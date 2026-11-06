"""Finite route-owner regressions. No host route or root installation effects."""
from __future__ import annotations

import copy
import importlib.util
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest


SOURCE = Path(__file__).resolve().parents[1] / "role_loopback.py"
if not SOURCE.exists():  # local staging before the exact files reach the source workspace
    SOURCE = Path(__file__).with_name("role_loopback.py")
spec = importlib.util.spec_from_file_location("hermes_role_loopback", SOURCE)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def route(alias):
    return [{"type": "local", "dst": alias, "dev": "lo", "protocol": "static",
             "scope": "host", "prefsrc": alias, "flags": []}]


IDENTITY = {"machine": "a" * 32, "boot": "a" * 36, "netns": [4, 123], "helper_sha256": "b" * 64}
CONTEXT = {
    "rules": [{"priority": 0, "src": "all", "table": "local"},
              {"priority": 32766, "src": "all", "table": "main"}],
    "loopback": {"ifindex": 1, "ifname": "lo", "flags": ["UP", "LOOPBACK"], "link_type": "loopback"},
    "ordinary": [{"type": "local", "dst": "127.0.0.0/8", "dev": "lo", "protocol": "kernel",
                  "scope": "host", "prefsrc": "127.0.0.1"}],
}


class Store:
    def __init__(self):
        self.value = None
        self.history = []
        self.fail_state = None

    def read(self):
        return copy.deepcopy(self.value)

    def save(self, value):
        if self.fail_state and any(e["state"] == self.fail_state for e in value["routes"].values()):
            raise OSError("simulated durable-write failure")
        self.value = copy.deepcopy(value)
        self.history.append(copy.deepcopy(value))


class Host:
    def __init__(self, store):
        self.store = store
        self.rows = {a: [] for a in m.ALIASES}
        self.ctx = copy.deepcopy(CONTEXT)
        self.commands = []
        self.stopped = True
        self.quiescence_calls = []
        self.source_ok = True
        self.effect = "success"
        self.change_after_first = False

    def context(self):
        return copy.deepcopy(self.ctx)

    def routes(self):
        return copy.deepcopy(self.rows)

    def sources(self):
        if not self.source_ok:
            raise m.Refusal("UNBOUND_SOURCE_SELECTION_UNQUALIFIED")

    def quiescent(self, *, rollback=False):
        self.quiescence_calls.append(rollback)
        if not self.stopped:
            raise m.Refusal("UNITS_NOT_QUIESCENT")

    def run(self, argv):
        self.commands.append(argv)
        alias, verb = argv[5].split("/")[0], argv[3]
        expected = "ADD_DISPATCHED" if verb == "add" else "DELETE_DISPATCHED"
        assert self.store.value["routes"][alias]["state"] == expected, "dispatch before durable intent"
        if self.effect == "refuse":
            return subprocess.CompletedProcess(argv, 2, b"", b"exists")
        self.rows[alias] = route(alias) if verb == "add" else []
        if self.change_after_first:
            self.rows[m.ALIASES[1]] = route(m.ALIASES[1])
        if self.effect == "lost_ack":
            raise m.Refusal("COMMAND_OUTCOME_UNAVAILABLE")
        if self.effect == "signal":
            return subprocess.CompletedProcess(argv, -9, b"", b"")
        if self.effect == "bad_postimage":
            self.rows[alias][0]["prefsrc"] = "127.0.0.1"
        return subprocess.CompletedProcess(argv, 0, b"", b"")


class RouteOwnerTests(unittest.TestCase):
    def setUp(self):
        self.store = Store()
        self.host = Host(self.store)

    def call(self, verb="ensure", identity=IDENTITY):
        return m.operate(verb, self.host, self.store, identity)

    def refused(self, verb="ensure", reason=None):
        with self.assertRaises(m.Refusal) as caught:
            self.call(verb)
        if reason:
            self.assertEqual(str(caught.exception), reason)

    def test_fixed_pair_preserves_ordinary_route_and_fsyncs_intent_before_each_add(self):
        result = self.call()
        self.assertEqual(result["status"], "SOURCE_SELECTION_QUALIFIED")
        self.assertEqual(self.host.commands, [m.route_command("add", a) for a in m.ALIASES])
        self.assertEqual(self.host.ctx, CONTEXT)
        self.assertEqual([e["state"] for e in self.store.value["routes"].values()], ["OWNED", "OWNED"])
        for alias in m.ALIASES:
            states = [r["routes"][alias]["state"] for r in self.store.history]
            self.assertLess(states.index("ADD_DISPATCHED"), states.index("ADD_ACKNOWLEDGED"))
            self.assertLess(states.index("ADD_ACKNOWLEDGED"), states.index("OWNED"))

    def test_repeat_ensure_verifies_without_any_second_mutation_or_required_role_stop(self):
        self.call()
        commands = copy.deepcopy(self.host.commands)
        self.host.stopped = False
        self.assertEqual(self.call()["status"], "SOURCE_SELECTION_QUALIFIED")
        self.assertEqual(self.host.commands, commands)

    def test_foreign_exact_static_route_is_not_adopted_or_deleted(self):
        self.host.rows[m.ALIASES[1]] = route(m.ALIASES[1])
        self.assertEqual(self.call("status")["routes"][m.ALIASES[1]], "EXTERNAL_EXACT")
        for verb in ("ensure", "rollback", "reconcile"):
            self.refused(verb)
        self.assertEqual(self.host.commands, [])
        self.assertIsNone(self.store.value)

    def test_second_prefix_conflict_prevents_any_first_prefix_effect(self):
        self.host.rows[m.ALIASES[1]] = route(m.ALIASES[1])
        self.host.rows[m.ALIASES[1]][0]["prefsrc"] = "127.0.0.1"
        self.refused()
        self.assertEqual(self.host.commands, [])

    def test_lost_add_ack_retains_unknown_and_matching_route_does_not_establish_ownership(self):
        self.host.effect = "lost_ack"
        self.refused()
        self.assertEqual(self.store.value["routes"][m.ALIASES[0]]["state"], "ADD_DISPATCHED")
        self.assertTrue(m.exact_route(self.host.rows[m.ALIASES[0]], m.ALIASES[0]))
        for verb in ("ensure", "reconcile", "rollback", "status"):
            self.refused(verb)
        self.assertEqual(len(self.host.commands), 1)

    def test_failed_ack_persistence_cannot_be_reconstructed_from_postimage(self):
        self.store.fail_state = "ADD_ACKNOWLEDGED"
        with self.assertRaises(OSError):
            self.call()
        self.store.fail_state = None
        self.refused("reconcile")
        self.refused()
        self.assertEqual(len(self.host.commands), 1)

    def test_durable_success_ack_can_reconcile_exact_postimage_without_route_mutation(self):
        self.store.fail_state = "OWNED"
        with self.assertRaises(OSError):
            self.call()
        self.store.fail_state = None
        self.assertEqual(self.store.value["routes"][m.ALIASES[0]]["state"], "ADD_ACKNOWLEDGED")
        self.assertEqual(self.call("reconcile")["routes"][m.ALIASES[0]], "OWNED")
        self.assertEqual(len(self.host.commands), 1)
        self.call()
        self.assertEqual(len(self.host.commands), 2)

    def test_positive_ack_wrong_postimage_stays_unqualified(self):
        self.host.effect = "bad_postimage"
        self.refused(reason="ACKNOWLEDGED_ROUTE_POSTIMAGE_MISMATCH")
        self.assertEqual(self.store.value["routes"][m.ALIASES[0]]["state"], "ADD_ACKNOWLEDGED")
        self.refused("reconcile")
        self.assertEqual(len(self.host.commands), 1)

    def test_known_command_refusal_is_retained_and_not_retried(self):
        self.host.effect = "refuse"
        self.refused()
        self.assertEqual(self.store.value["routes"][m.ALIASES[0]]["state"], "ADD_REFUSED")
        self.refused()
        self.refused("rollback")
        self.assertEqual(len(self.host.commands), 1)

    def test_successful_add_but_lookup_failure_preserves_known_owned_routes(self):
        self.host.source_ok = False
        self.refused(reason="UNBOUND_SOURCE_SELECTION_UNQUALIFIED")
        self.assertTrue(all(e["state"] == "OWNED" for e in self.store.value["routes"].values()))
        self.host.source_ok = True
        self.call()
        self.assertEqual(len(self.host.commands), 2)

    def test_signalled_command_never_becomes_negative_kernel_ack(self):
        self.host.effect = "signal"
        self.refused(reason="COMMAND_TERMINATED_ACK_UNKNOWN")
        entry = self.store.value["routes"][m.ALIASES[0]]
        self.assertEqual(entry["state"], "ADD_DISPATCHED")
        self.assertIsNone(entry["ack"])
        self.refused("reconcile")
        self.refused()
        self.assertEqual(len(self.host.commands), 1)

    def test_route_or_context_change_during_lookup_cannot_return_success(self):
        self.call()
        pristine_rows = copy.deepcopy(self.host.rows)
        for verb in ("ensure", "status"):
            for change_context in (False, True):
                self.host.rows, self.host.ctx = copy.deepcopy(pristine_rows), copy.deepcopy(CONTEXT)
                def change():
                    if change_context:
                        self.host.ctx["ordinary"][0]["prefsrc"] = "127.0.0.5"
                    else:
                        self.host.rows[m.ALIASES[0]] = []
                self.host.sources = change
                with self.subTest(verb=verb, context=change_context):
                    self.refused(verb)
        self.assertEqual(len(self.host.commands), 2)

    def test_numeric_equality_cannot_hide_receipt_type_drift(self):
        self.call()
        pristine = copy.deepcopy(self.store.value)
        self.store.value["identity"]["netns"] = [4.0, 123.0]
        self.refused("status")
        self.store.value = pristine
        self.store.value["context"]["rules"][0]["priority"] = False
        self.refused("status")

    def test_running_roles_prevent_initial_mutation(self):
        self.host.stopped = False
        self.refused(reason="UNITS_NOT_QUIESCENT")
        self.assertEqual(self.host.commands, [])
        self.assertIsNone(self.store.value)

    def test_foreign_change_between_prefixes_stops_without_auto_rollback(self):
        self.host.change_after_first = True
        self.refused(reason="UNOWNED_ROUTE_PRESENT")
        self.assertEqual(len(self.host.commands), 1)
        self.assertEqual(self.store.value["routes"][m.ALIASES[0]]["state"], "OWNED")

    def test_source_boot_machine_or_namespace_change_cannot_reuse_ownership(self):
        self.call()
        for key, value in (("machine", "c" * 32), ("boot", "new-boot"), ("netns", [4, 456]),
                           ("helper_sha256", "d" * 64)):
            with self.subTest(key=key):
                identity = {**IDENTITY, key: value}
                with self.assertRaises(m.Refusal):
                    self.call(identity=identity)
        self.assertEqual(len(self.host.commands), 2)

    def test_rule_or_ordinary_route_change_prevents_rollback(self):
        self.call()
        self.host.ctx["ordinary"][0]["prefsrc"] = "127.0.0.5"
        self.refused("rollback")
        self.assertEqual(len(self.host.commands), 2)

    def test_same_zero_priority_filter_or_duplicate_priority_is_refused(self):
        for rule in ({"priority": 0, "src": "all", "table": "local", "uidrange": "0-0"},
                     {"priority": 0, "src": "all", "table": "main"}):
            with self.subTest(rule=rule):
                self.host.ctx = copy.deepcopy(CONTEXT)
                self.host.ctx["rules"].insert(0, rule)
                self.refused()
        self.assertEqual(self.host.commands, [])

    def test_rollback_is_explicit_reverse_exact_deletion_and_retains_receipt(self):
        self.call()
        result = self.call("rollback")
        self.assertEqual(result["status"], "ROLLED_BACK")
        self.assertEqual(self.host.commands[2:], [m.route_command("del", a) for a in reversed(m.ALIASES)])
        self.assertTrue(all(self.host.rows[a] == [] for a in m.ALIASES))
        self.assertEqual(self.host.ctx, CONTEXT)
        self.refused(reason="ROLLED_BACK_TRANSACTION_RETAINED")
        self.assertEqual(len(self.host.commands), 4)

    def test_rollback_closes_never_dispatched_transaction_without_inventing_delete(self):
        self.store.fail_state = "ADD_DISPATCHED"
        with self.assertRaises(OSError):
            self.call()
        self.assertEqual(self.host.commands, [])
        self.store.fail_state = None
        self.assertEqual(self.call("rollback")["status"], "ROLLED_BACK")
        for entry in self.store.value["routes"].values():
            self.assertEqual(entry["state"], "CANCELLED")
            self.assertIsNone(entry["dispatch"])
            self.assertIsNone(entry["ack"])
        self.refused(reason="ROLLED_BACK_TRANSACTION_RETAINED")
        self.assertEqual(self.host.commands, [])

    def test_rollback_requires_roles_and_proxy_stopped(self):
        self.call()
        self.host.stopped = False
        self.refused("rollback", "UNITS_NOT_QUIESCENT")
        self.assertEqual(len(self.host.commands), 2)

    def test_rollback_never_deletes_replaced_owned_route(self):
        self.call()
        self.host.rows[m.ALIASES[1]][0]["protocol"] = "boot"
        self.refused("rollback", "OWNED_ROUTE_CHANGED")
        self.assertEqual(len(self.host.commands), 2)

    def test_lost_delete_ack_blocks_any_add_or_second_delete(self):
        self.call()
        self.host.effect = "lost_ack"
        self.refused("rollback")
        self.assertEqual(self.store.value["routes"][m.ALIASES[1]]["state"], "DELETE_DISPATCHED")
        for verb in ("ensure", "rollback", "reconcile"):
            self.refused(verb)
        self.assertEqual(len(self.host.commands), 3)

    def test_acknowledged_delete_reconciles_absence_without_repeating_delete(self):
        self.call()
        self.store.fail_state = "REMOVED"
        with self.assertRaises(OSError):
            self.call("rollback")
        self.store.fail_state = None
        self.call("reconcile")
        self.call("rollback")
        self.assertEqual(len(self.host.commands), 4)

    def test_tampered_command_or_boolean_ack_cannot_establish_ownership(self):
        self.call()
        pristine = copy.deepcopy(self.store.value)
        for member, value in (("ack", False), ("dispatch", ["ip", "route", "flush"]),
                              ("before", route(m.ALIASES[0]))):
            with self.subTest(member=member):
                self.store.value = copy.deepcopy(pristine)
                self.store.value["routes"][m.ALIASES[0]][member] = value
                self.refused("status")

    def test_no_arbitrary_route_or_command_surface(self):
        for verb, alias in (("replace", m.ALIASES[0]), ("flush", m.ALIASES[0]),
                            ("add", "127.0.0.0/8"), ("del", "0.0.0.0/0")):
            with self.assertRaises(m.Refusal):
                m.route_command(verb, alias)
        self.refused("install")

    def test_extra_route_attributes_or_multiple_rows_are_conflicts(self):
        alias = m.ALIASES[0]
        for rows in (route(alias) * 2, [{**route(alias)[0], "gateway": "127.0.0.1"}],
                     [{**route(alias)[0], "flags": ["linkdown"]}]):
            self.assertFalse(m.exact_route(rows, alias))

    def test_duplicate_or_unbounded_json_is_refused(self):
        for raw in ('{"x":1,"x":2}', '{"x":NaN}', ' ' * (m.MAX_BYTES + 1)):
            with self.assertRaises(m.Refusal):
                m.decode(raw)


class UnitContractTests(unittest.TestCase):
    def test_actual_iproute_lookup_forms_require_correct_unbound_source(self):
        host = m.LinuxHost()
        for table in (None, "local"):
            def query(argv):
                alias = argv[-1]
                row = {"type": "local", "dst": alias, "dev": "lo", "prefsrc": alias,
                       "flags": [], "uid": 0, "cache": ["local"]}
                if table is not None:
                    row["table"] = table
                return [row]
            host.query = query
            host.sources()
        for change in ({"table": "main"}, {"prefsrc": "127.0.0.1"}, {"gateway": "127.0.0.1"},
                       {"dev": "eth0"}, {"type": "unicast"}, {"flags": ["linkdown"]}):
            def query(argv):
                alias = argv[-1]
                return [{"type": "local", "dst": alias, "dev": "lo", "prefsrc": alias, **change}]
            host.query = query
            with self.subTest(change=change), self.assertRaises(m.Refusal):
                host.sources()

    def test_condition_is_fixed_root_command_and_main_proxy_stays_unprivileged(self):
        unit_path = SOURCE.with_name("hermes-egress.service")
        if not unit_path.exists():
            self.skipTest("source unit not present in local staging")
        unit = unit_path.read_text()
        active = [line.strip() for line in unit.splitlines() if line and not line.startswith("#")]
        conditions = [line for line in active if line.startswith("ExecCondition=")]
        self.assertEqual(conditions, ["ExecCondition=+/usr/bin/python3 -I -S /usr/local/libexec/mastermind-hermes-loopback.py ensure"])
        for line in ("User=proxy", "Group=proxy", "NoNewPrivileges=yes", "CapabilityBoundingSet=",
                     "AmbientCapabilities=", "RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6"):
            self.assertIn(line, active)
        self.assertFalse(any(line.startswith(("ExecStop=", "ExecStopPost=", "SuccessExitStatus=")) for line in active))
        self.assertNotIn("AF_NETLINK", unit)


@unittest.skipUnless(sys.platform.startswith("linux") and os.geteuid() == 0,
                     "real root-only receipt custody requires an isolated Linux root test environment")
class RootStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="mmx-route-test-", dir="/run")
        self.directory = Path(self.tmp.name) / "owner"

    def tearDown(self):
        self.tmp.cleanup()

    def test_real_private_atomic_receipt_and_stable_exclusive_lock(self):
        with m.RootStore(self.directory) as store:
            self.assertIsNone(store.read())
            store.save({"phase": "before"})
            self.assertEqual(store.read(), {"phase": "before"})
            lock_inode = (self.directory / "lock").stat().st_ino
            with self.assertRaises(BlockingIOError):
                with m.RootStore(self.directory):
                    self.fail("second writer acquired lock")
            store.save({"phase": "after"})
            self.assertEqual((self.directory / "lock").stat().st_ino, lock_inode)
            self.assertEqual(stat.S_IMODE((self.directory / "receipt.json").stat().st_mode), 0o600)
            self.assertEqual(sorted(p.name for p in self.directory.iterdir()), ["lock", "receipt.json"])

    def test_foreign_file_between_read_and_write_is_preserved(self):
        with m.RootStore(self.directory) as store:
            store.read()
            target = self.directory / "receipt.json"
            target.write_text('{"foreign":true}\n')
            target.chmod(0o600)
            before = target.read_bytes()
            with self.assertRaises(m.Refusal):
                store.save({"ours": True})
            self.assertEqual(target.read_bytes(), before)

    def test_symlink_and_world_readable_receipt_are_refused_without_replacement(self):
        with m.RootStore(self.directory) as store:
            store.read()
            other = Path(self.tmp.name) / "other"
            other.write_text("unchanged")
            target = self.directory / "receipt.json"
            target.symlink_to(other)
            with self.assertRaises(OSError):
                store.read()
            self.assertEqual(other.read_text(), "unchanged")
            target.unlink()
            target.write_text('{}\n')
            target.chmod(0o644)
            with self.assertRaises(m.Refusal):
                store.read()

    def test_proxy_writable_state_directory_is_refused(self):
        self.directory.mkdir(mode=0o777)
        self.directory.chmod(0o777)
        with self.assertRaises(m.Refusal):
            with m.RootStore(self.directory):
                self.fail("unsafe directory accepted")

    def test_replaced_lock_or_hardlinked_receipt_cannot_be_used(self):
        with m.RootStore(self.directory) as store:
            store.read()
            store.save({"owned": True})
            os.link(self.directory / "receipt.json", self.directory / "foreign-link")
            with self.assertRaises(m.Refusal):
                store.read()
            (self.directory / "foreign-link").unlink()
            (self.directory / "lock").unlink()
            (self.directory / "lock").touch(mode=0o600)
            with self.assertRaises(m.Refusal):
                store.save({"must_not_write": True})
            self.assertEqual(json.loads((self.directory / "receipt.json").read_text()), {"owned": True})


if __name__ == "__main__":
    unittest.main()

"""Pure integrity and bounded Event-query negatives.

The disposable events table tests this helper's SQL/data boundary only. It is
not a synthetic Runtime admission or a replacement for the joined owner test.
"""
import copy
import sqlite3
import unittest

from common import direct_native_result_contract as c
from control_plane import direct_native_result as subject


class DirectResultIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.selection = dict(work_ref="WS:H2", job_id="JOB-h2", attempt_id="ATT-h2")
        self.identity = dict(principal_scope="1" * 64, receiver_binding_digest="2" * 64,
                             source_digest="3" * 64, admission_digest="4" * 64)
        self.payload = dict(summary="Actual retained findings", current_state="Complete",
                            completed_steps=[], next_actions=[])
        self.record = dict(schema_version="test-only-raw-integrity", payload=self.payload)
        self.completion = dict(payload=copy.deepcopy(self.payload),
            terminal_record=copy.deepcopy(self.record), terminal_digest=c.digest(self.record))

    def test_changed_payload_or_terminal_record_cannot_keep_original_digest(self):
        self.assertEqual(subject._completion(self.completion), self.completion)
        for field in ("payload", "terminal_record"):
            changed = copy.deepcopy(self.completion)
            target = changed[field] if field == "payload" else changed[field]["payload"]
            target["summary"] = "forged"
            with self.subTest(field=field), self.assertRaises(subject.DirectResultProjectionError):
                subject._completion(changed)

    def test_constructor_mapping_is_not_a_runtime_snapshot(self):
        with self.assertRaises(subject.DirectResultProjectionError):
            subject.project_direct_native_result(dict(self.completion), {})

    def test_consumption_key_binds_original_identity_and_operation(self):
        original = subject.consumption_command_id("consume-one", self.identity)
        self.assertEqual(original, subject.consumption_command_id("consume-one", copy.deepcopy(self.identity)))
        for key in self.identity:
            changed = dict(self.identity, **{key: "f" * 64})
            self.assertNotEqual(original, subject.consumption_command_id("consume-one", changed))
        self.assertNotEqual(original, subject.consumption_command_id("consume-two", self.identity))

    def query(self, *, mutated=None, raw=None, duplicates=1):
        connection = sqlite3.connect(":memory:"); connection.row_factory = sqlite3.Row
        self.addCleanup(connection.close)
        connection.execute("CREATE TABLE events(event_id INTEGER PRIMARY KEY, command_id TEXT, "
            "aggregate_type TEXT,aggregate_id TEXT,event_type TEXT,actor TEXT,job_id TEXT,attempt_id TEXT,payload_json TEXT)")
        payload = dict(schema=subject.CONSUMPTION_SCHEMA, selection=self.selection,
                       result_digest=self.completion["terminal_digest"], identity=self.identity,
                       operation_key="consume-one")
        if mutated:
            payload.update(mutated)
        encoded = raw if raw is not None else c.canonical_bytes(payload).decode()
        for i in range(duplicates):
            connection.execute("INSERT INTO events VALUES(?,?,?,?,?,?,?,?,?)", (
                i + 1, subject.consumption_command_id("consume-one", self.identity), "job", "JOB-h2",
                subject.EVENT_TYPE, "direct-native-parent", "JOB-h2", "ATT-h2", encoded))
        return subject.direct_consumption_state(connection, self.selection, self.identity,
                                                 self.completion["terminal_digest"])

    def test_absent_event_is_unconsumed_and_exact_event_is_consumed(self):
        self.assertEqual(self.query(duplicates=0), dict(state="UNCONSUMED", receipt_digest=None))
        value = self.query()
        self.assertEqual(value["state"], "CONSUMED")
        c.hex_digest(value["receipt_digest"])

    def test_wrong_parent_source_or_terminal_and_duplicate_event_refuse(self):
        for changes in (dict(identity=dict(self.identity, receiver_binding_digest="f" * 64)),
                        dict(identity=dict(self.identity, source_digest="f" * 64)),
                        dict(result_digest="f" * 64), dict(operation_key="another-operation")):
            with self.subTest(changes=changes), self.assertRaises(subject.DirectResultProjectionError):
                self.query(mutated=changes)
        with self.assertRaises(subject.DirectResultProjectionError):
            self.query(duplicates=2)

    def test_noncanonical_duplicate_and_overbudget_event_are_not_consumption(self):
        for raw in ('{"schema":1,"schema":2}', '{ "schema": 1 }',
                    c.canonical_bytes({"secret_sentinel": "DO_NOT_RETURN" * 400}).decode()):
            with self.subTest(length=len(raw)), self.assertRaises(subject.DirectResultProjectionError) as raised:
                self.query(raw=raw)
            self.assertNotIn("DO_NOT_RETURN", str(raised.exception))


if __name__ == "__main__":
    unittest.main()

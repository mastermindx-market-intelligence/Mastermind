import hashlib
from control_plane.codex_progress_metadata import _IDENTITY_MAX_CHARS, ProgressMetadata, decode_progress, _PLAN_MAX_STEPS, _SUMMARY_MAX_CHARS, _TOOL_ITEM_TYPES
import dataclasses
import unittest

_THREAD = "thread-selfcheck-0001"
_TURN = "turn-selfcheck-0002"

def _plan_params(plan, **extra):
    params = {"threadId": _THREAD, "turnId": _TURN, "plan": plan}
    params.update(extra)
    return params

def _item_params(item, started=True, **extra):
    params = {"threadId": _THREAD, "turnId": _TURN, "item": item}
    params["startedAtMs" if started else "completedAtMs"] = 1700000000000
    params.update(extra)
    return params

class DecodeProgressSelfCheck(unittest.TestCase):
    def test_authored_plan_counts_and_fixed_identity(self):
        meta = decode_progress(
            "turn/plan/updated",
            _plan_params([
                {"step": "alpha", "status": "pending"},
                {"step": "beta", "status": "inProgress"},
                {"step": "gamma", "status": "completed"},
                {"step": "delta", "status": "completed"},
            ]),
            thread_id=_THREAD,
            turn_id=_TURN,
        )
        self.assertIsInstance(meta, ProgressMetadata)
        self.assertEqual(meta.source_item_id, "authored-plan")
        self.assertEqual(meta.kind, "plan")
        self.assertEqual(meta.state, "partial")
        self.assertEqual(
            meta.summary,
            "authored plan (non-executable): 1 pending, 1 in progress, 2 completed",
        )

    def test_fully_completed_authored_plan_stays_partial(self):
        meta = decode_progress(
            "turn/plan/updated",
            _plan_params([{"step": "only", "status": "completed"}]),
            thread_id=_THREAD,
            turn_id=_TURN,
        )
        self.assertEqual(meta.state, "partial")
        self.assertIn("0 pending, 0 in progress, 1 completed", meta.summary)

    def test_all_nine_tool_types_recognized(self):
        for item_type in sorted(_TOOL_ITEM_TYPES):
            with self.subTest(item_type=item_type):
                meta = decode_progress(
                    "item/started",
                    _item_params({"id": "native-1", "type": item_type}),
                    thread_id=_THREAD,
                    turn_id=_TURN,
                )
                self.assertEqual(meta.kind, item_type)
                self.assertEqual(meta.state, "partial")
                self.assertEqual(meta.summary, "tool started")

    def test_item_identity_hashed_and_completed_outcome_unverified(self):
        native = "item/native-xyz"
        meta = decode_progress(
            "item/completed",
            _item_params(
                {"id": native, "type": "commandExecution"},
                started=False,
                startedAtMs=1699999999999,  # stray extra field: ignored
            ),
            thread_id=_THREAD,
            turn_id=_TURN,
        )
        self.assertEqual(
            meta.source_item_id,
            "sha256:" + hashlib.sha256(native.encode("utf-8")).hexdigest(),
        )
        self.assertNotIn(native, meta.source_item_id)
        self.assertEqual(meta.kind, "commandExecution")
        self.assertEqual(meta.state, "completed")
        self.assertEqual(meta.summary, "tool lifecycle completed; outcome unverified")

    def test_null_and_zero_timestamps_accepted(self):
        self.assertIsNotNone(decode_progress(
            "item/started",
            _item_params({"id": "i", "type": "sleep"}, startedAtMs=None),
            thread_id=_THREAD,
            turn_id=_TURN,
        ))
        self.assertIsNotNone(decode_progress(
            "item/completed",
            _item_params({"id": "i", "type": "sleep"}, started=False, completedAtMs=0),
            thread_id=_THREAD,
            turn_id=_TURN,
        ))

    def test_unknown_methods_ignored(self):
        for method in ("item/updated", "item/reasoning", "turn/aborted",
                       "reasoning/textDelta", ""):
            with self.subTest(method=method):
                self.assertIsNone(decode_progress(
                    method,
                    {"threadId": _THREAD, "turnId": _TURN},
                    thread_id=_THREAD,
                    turn_id=_TURN,
                ))

    def test_unknown_item_types_ignored(self):
        for item_type in ("reasoning", "bogusTool", "webSearch2"):
            with self.subTest(item_type=item_type):
                self.assertIsNone(decode_progress(
                    "item/started",
                    _item_params({"id": "n", "type": item_type}),
                    thread_id=_THREAD,
                    turn_id=_TURN,
                ))
        self.assertIsNone(decode_progress(  # type missing entirely
            "item/completed",
            _item_params({"id": "n"}, started=False),
            thread_id=_THREAD,
            turn_id=_TURN,
        ))
        self.assertIsNone(decode_progress(  # ignored before id is checked
            "item/started",
            _item_params({"id": "", "type": "reasoning"}),
            thread_id=_THREAD,
            turn_id=_TURN,
        ))

    def test_foreign_thread_or_turn_refused(self):
        for kwargs in (
            {"thread_id": "thread-other", "turn_id": _TURN},
            {"thread_id": _THREAD, "turn_id": "turn-other"},
        ):
            with self.subTest(**kwargs):
                with self.assertRaises(ValueError):
                    decode_progress("turn/plan/updated", _plan_params([]), **kwargs)
                with self.assertRaises(ValueError):
                    decode_progress(
                        "item/started",
                        _item_params({"id": "n", "type": "webSearch"}),
                        **kwargs,
                    )

    def test_params_identity_mismatch_refused(self):
        for params in (
            {"threadId": "thread-other", "turnId": _TURN, "plan": []},
            {"threadId": _THREAD, "turnId": "turn-other", "plan": []},
            {"threadId": _THREAD.upper(), "turnId": _TURN, "plan": []},
        ):
            with self.subTest(params=params):
                with self.assertRaises(ValueError):
                    decode_progress("turn/plan/updated", params, thread_id=_THREAD, turn_id=_TURN)

    def test_invalid_expected_identity_refused(self):
        for kwargs in (
            {"thread_id": "", "turn_id": _TURN},
            {"thread_id": None, "turn_id": _TURN},
            {"thread_id": "t" * 257, "turn_id": _TURN},
            {"thread_id": _THREAD, "turn_id": 7},
            {"thread_id": _THREAD, "turn_id": "u" * 257},
        ):
            with self.subTest(**kwargs):
                with self.assertRaises(ValueError):
                    decode_progress("turn/plan/updated", _plan_params([]), **kwargs)

    def test_identity_bounds_accepted_at_limit(self):
        ok_thread = "t" * _IDENTITY_MAX_CHARS
        ok_turn = "u" * _IDENTITY_MAX_CHARS
        meta = decode_progress(
            "turn/plan/updated",
            {"threadId": ok_thread, "turnId": ok_turn, "plan": []},
            thread_id=ok_thread,
            turn_id=ok_turn,
        )
        self.assertEqual(meta.kind, "plan")
        ok_item = "n" * _IDENTITY_MAX_CHARS
        meta = decode_progress(
            "item/started",
            _item_params({"id": ok_item, "type": "webSearch"}),
            thread_id=_THREAD,
            turn_id=_TURN,
        )
        self.assertEqual(len(meta.source_item_id), len("sha256:") + 64)

    def test_empty_plan_counts_zero(self):
        meta = decode_progress(
            "turn/plan/updated", _plan_params([]), thread_id=_THREAD, turn_id=_TURN
        )
        self.assertEqual(
            meta.summary,
            "authored plan (non-executable): 0 pending, 0 in progress, 0 completed",
        )

    def test_malformed_recognized_payloads_refused(self):
        good_item = {"id": "n", "type": "webSearch"}
        oversize_plan = [
            {"step": "s", "status": "pending"} for _ in range(_PLAN_MAX_STEPS + 1)
        ]
        cases = [
            ("params not a mapping", "item/started", ["nope"]),
            ("params identity not a string", "turn/plan/updated",
             {"threadId": 5, "turnId": _TURN, "plan": []}),
            ("params identity empty", "turn/plan/updated",
             {"threadId": "", "turnId": _TURN, "plan": []}),
            ("params identity oversized", "turn/plan/updated",
             {"threadId": "t" * 257, "turnId": _TURN, "plan": []}),
            ("plan missing", "turn/plan/updated",
             {"threadId": _THREAD, "turnId": _TURN}),
            ("plan not a list", "turn/plan/updated",
             {"threadId": _THREAD, "turnId": _TURN,
              "plan": {"0": {"step": "s", "status": "pending"}}}),
            ("plan entry not a mapping", "turn/plan/updated", _plan_params(["pending"])),
            ("plan step not a string", "turn/plan/updated",
             _plan_params([{"step": 1, "status": "pending"}])),
            ("plan status unknown", "turn/plan/updated",
             _plan_params([{"step": "s", "status": "done"}])),
            ("plan status bool", "turn/plan/updated",
             _plan_params([{"step": "s", "status": True}])),
            ("plan status not a string", "turn/plan/updated",
             _plan_params([{"step": "s", "status": 3}])),
            ("plan status missing", "turn/plan/updated", _plan_params([{"step": "s"}])),
            ("oversized plan", "turn/plan/updated", _plan_params(oversize_plan)),
            ("item missing", "item/started",
             {"threadId": _THREAD, "turnId": _TURN, "startedAtMs": None}),
            ("item not a mapping", "item/started",
             {"threadId": _THREAD, "turnId": _TURN, "item": "x",
              "startedAtMs": None}),
            ("item id missing", "item/started",
             _item_params({"type": "webSearch"})),
            ("item id empty", "item/started",
             _item_params({"id": "", "type": "webSearch"})),
            ("item id oversized", "item/started",
             _item_params({"id": "x" * 257, "type": "webSearch"})),
            ("item id not a string", "item/completed",
             _item_params({"id": 9, "type": "webSearch"}, started=False)),
            ("bool timestamp", "item/started",
             _item_params(good_item, startedAtMs=True)),
            ("float timestamp", "item/started",
             _item_params(good_item, startedAtMs=1.5)),
            ("string timestamp", "item/completed",
             _item_params(good_item, started=False, completedAtMs="1700000000000")),
            ("timestamp missing", "item/completed",
             {"threadId": _THREAD, "turnId": _TURN, "item": good_item}),
        ]
        for name, method, params in cases:
            with self.subTest(case=name):
                with self.assertRaises(ValueError):
                    decode_progress(method, params, thread_id=_THREAD, turn_id=_TURN)
        with self.subTest(case="method not a string"):
            with self.assertRaises(ValueError):
                decode_progress(
                    7,
                    {"threadId": _THREAD, "turnId": _TURN},
                    thread_id=_THREAD,
                    turn_id=_TURN,
                )

    def test_metadata_frozen(self):
        meta = decode_progress(
            "turn/plan/updated", _plan_params([]), thread_id=_THREAD, turn_id=_TURN
        )
        with self.assertRaises(dataclasses.FrozenInstanceError):
            meta.kind = "tool"

    def test_private_payload_never_leaks_into_output(self):
        secret_command = "SECRET-COMMAND-88"
        secret_output = "SECRET-OUTPUT-42"
        secret_explanation = "SECRET-EXPLANATION-7"
        secret_step = "SECRET-STEP-13"
        item = {
            "id": "SECRET-NATIVE-ID",
            "type": "commandExecution",
            "command": [secret_command],
            "cwd": "/etc",
            "aggregatedOutput": secret_output,
            "exitCode": 0,
            "toolName": "SECRET-TOOL-NAME",
        }
        params = _item_params(item, started=True, explanation=secret_explanation)
        meta = decode_progress("item/started", params, thread_id=_THREAD, turn_id=_TURN)
        rendered = repr(meta) + "".join(dataclasses.astuple(meta))
        for secret in (secret_command, secret_output, secret_explanation,
                       "SECRET-NATIVE-ID", "SECRET-TOOL-NAME", "/etc"):
            self.assertNotIn(secret, rendered)
        plan_meta = decode_progress(
            "turn/plan/updated",
            _plan_params(
                [{"step": secret_step, "status": "inProgress"}],
                explanation=secret_explanation,
            ),
            thread_id=_THREAD,
            turn_id=_TURN,
        )
        plan_rendered = repr(plan_meta) + "".join(dataclasses.astuple(plan_meta))
        for secret in (secret_step, secret_explanation):
            self.assertNotIn(secret, plan_rendered)

    def test_summary_bounded_for_maximum_plan(self):
        plan = [{"step": "x" * 4096, "status": "completed"} for _ in range(_PLAN_MAX_STEPS)]
        meta = decode_progress(
            "turn/plan/updated",
            _plan_params(plan, explanation="x" * 4096),
            thread_id=_THREAD,
            turn_id=_TURN,
        )
        self.assertLessEqual(len(meta.summary), _SUMMARY_MAX_CHARS)
        self.assertEqual(
            meta.summary,
            "authored plan (non-executable): 0 pending, 0 in progress, 128 completed",
        )



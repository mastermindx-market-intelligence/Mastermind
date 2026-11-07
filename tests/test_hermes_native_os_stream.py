"""Real native event shapes; no service, provider, credentials or admissions."""
import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
import unittest
from tests.test_hermes_native_os_bridge import load, identity


def receipt(status="started", generation=4):
    return {"ref": {"session_id": "session-1", "authority_epoch": 2}, "admission_id": "original",
            "status": status, "sequence": 1, "execution_generation": generation, "outcome": None}


def event(seq, text="", kind="message.delta", **extra):
    return {"seq": seq, "session_id": "session-1", "admission_id": "original", "authority_epoch": 2,
            "execution_generation": 4, "replay_epoch": "epoch-one", "type": kind,
            "payload": {"text": text}, **extra}


def batch(events, latest=None, **extra):
    return {"replay_epoch": "epoch-one", "snapshot_required": False, "truncated": False,
            "latest_seq": max((e["seq"] for e in events), default=0) if latest is None else latest,
            "events": events, **extra}


class StreamProjectionTests(unittest.TestCase):
    def setUp(self):
        self.b = load()
        self.p = self.b.NativeStreamProjection("session-1", "original", 2)
        self.p.bind_replay({"replay_epoch": "epoch-one"})
        self.p.receipt(receipt())

    def test_real_utf16_offsets_deduplicate_replayed_and_overlapping_chunks(self):
        def delta(seq, text, offset):
            return event(seq, payload={"turn_id": "turn-one", "segment": 0, "offset": offset, "text": text})
        first = delta(1, "Hi 🌱", 0)
        self.p.apply(batch([first]))
        self.p.apply(batch([first, delta(2, "🌱 there", 3)]))
        self.assertEqual(self.p.text, "Hi 🌱 there")
        self.p.apply(batch([delta(3, " there", 5)]))
        self.assertEqual(self.p.text, "Hi 🌱 there")

    def test_null_delta_and_sealed_segments_do_not_duplicate_reply(self):
        self.p.apply(batch([event(1, "First"), event(2, payload={"text": None}),
            event(3, "First", "message.interim"), event(4, "Second"), event(5, "Second", "message.complete")]))
        self.assertEqual(self.p.text, "First\n\nSecond")
        self.assertEqual(self.p.frame()["state"], "live")  # complete event is not a terminal receipt

    def test_foreign_admission_and_reasoning_or_tool_payloads_never_cross(self):
        self.p.apply(batch([event(1, "foreign private", admission_id="another"),
            event(2, "private reasoning", "reasoning.delta"), event(3, "private tool result", "tool.complete"),
            event(4, "Public answer")]))
        self.assertEqual(self.p.text, "Public answer")
        self.assertNotIn("private", str(self.p.frame()))

    def test_crossed_session_epoch_authority_or_execution_is_rejected(self):
        for override in [{"session_id": "crossed"}, {"authority_epoch": 3}, {"execution_generation": 5}, {"replay_epoch": "new-epoch"}]:
            with self.subTest(override=override), self.assertRaises(self.b.BridgeRefusal):
                self.p.apply(batch([event(1, "wrong", **override)]))
        self.assertEqual(self.p.text, "")

    def test_replay_gap_or_regression_never_extrapolates(self):
        for change in [{"snapshot_required": True}, {"truncated": True}, {"replay_epoch": "other"}]:
            with self.subTest(change=change), self.assertRaises(self.b.BridgeRefusal):
                self.p.apply(batch([event(1, "unsafe")], **change))
        self.p.apply(batch([event(1, "kept")]))
        with self.assertRaises(self.b.BridgeRefusal): self.p.apply(batch([], latest=0))
        self.assertEqual(self.p.text, "kept")

    def test_missing_or_conflicting_utf16_prefix_is_rejected(self):
        self.p.apply(batch([event(1, payload={"turn_id": "turn", "segment": 0, "offset": 0, "text": "prefix"})]))
        for offset, text in [(20, "tail"), (0, "wrong")]:
            with self.subTest(offset=offset), self.assertRaises(self.b.BridgeRefusal):
                self.p.apply(batch([event(2, payload={"turn_id": "turn", "segment": 0, "offset": offset, "text": text})]))

    def test_unqualified_receipt_cannot_settle_or_change_binding(self):
        for bad in [{**receipt(), "admission_id": "foreign"}, receipt(generation=5),
                    {**receipt(), "ref": {"session_id": "session-1", "authority_epoch": 3}}]:
            with self.subTest(bad=bad), self.assertRaises(self.b.BridgeRefusal): self.p.receipt(bad)

    def test_display_and_batch_budgets_are_bounded(self):
        with self.assertRaises(self.b.BridgeRefusal): self.p.apply(batch([event(1, "x" * 262145)]))
        with self.assertRaises(self.b.BridgeRefusal): self.p.apply(batch([event(1)] * 4097))


class ObserveTests(unittest.IsolatedAsyncioTestCase):
    async def test_single_read_connection_never_attaches_retries_or_submits(self):
        b = load()
        class Runtime:
            home = Path("/fixture/hermes")
            calls = []
            receipts = 0
            def require_stream_source(self): pass
            async def identify(self): return identity()
            @asynccontextmanager
            async def connect(self, _endpoint): yield self
            async def rpc(self, method, **params):
                self.calls.append((method, params))
                if method == "prompt.receipt":
                    self.receipts += 1
                    return receipt("terminal" if self.receipts == 2 else "started")
                if method == "session.events.since":
                    if "replay_epoch" not in params: return batch([], snapshot_required=True)
                    return batch([event(1, "Real streamed answer")] if params["last_sequence"] == 0 else [], latest=1)
                raise AssertionError("unexpected mutation or lifecycle call")
        runtime, frames = Runtime(), []
        await b.observe_request({"operation": "observe", "sessionId": "session-1", "admissionId": "original", "authorityEpoch": 2}, runtime, frames.append, duration=1, interval=0)
        self.assertEqual([f["state"] for f in frames], ["live", "complete"])
        self.assertEqual(frames[-1]["text"], "Real streamed answer")
        self.assertEqual({c[0] for c in runtime.calls}, {"prompt.receipt", "session.events.since"})

    async def test_replay_loss_stops_observation_and_never_signals_completion(self):
        b = load()
        class Runtime:
            home = Path("/fixture/hermes")
            def require_stream_source(self): pass
            async def identify(self): return identity()
            @asynccontextmanager
            async def connect(self, _endpoint): yield self
            async def rpc(self, method, **params):
                if method == "prompt.receipt": return receipt()
                return batch([], snapshot_required=True)
        frames = []
        await b.observe_request({"operation": "observe", "sessionId": "session-1", "admissionId": "original", "authorityEpoch": 2}, Runtime(), frames.append, duration=1, interval=0)
        self.assertEqual(frames[-1]["state"], "interrupted")
        self.assertEqual(frames[-1]["code"], "NATIVE_STREAM_GAP")


if __name__ == "__main__": unittest.main()

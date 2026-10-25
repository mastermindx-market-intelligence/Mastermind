from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from detect import classify, scan
from fixture_loader import load_fixture
from roster import default_roster, roster_with
from shadow import collect_messages


class CommissionDetection(unittest.TestCase):
    def setUp(self):
        self.client, self.ledger = load_fixture()
        self.roster = roster_with(other_seats=("U0OTHERSEAT1",))
        self.messages = collect_messages(
            self.client,
            (
                "C0BSBM78V1N",
                "C0BTD5804QK",
                "C0BRDFZPLHK",
                "C0C5FCK1F45",
                "C0CBC6AEAQZ",
                "C0CCNK7JFAL",
            ),
        )

    def test_ping_scan_decisions_match_the_fixture(self):
        decisions = scan(
            self.messages,
            channels=("C0BSBM78V1N", "C0BTD5804QK", "C0BRDFZPLHK", "C0C5FCK1F45", "C0CBC6AEAQZ"),
            include_returns=True,
            ledger=self.ledger,
            roster=self.roster,
            seen=set(),
        )
        kinds = [(item["channel"], item["ts"], item["decision"]) for item in decisions]
        self.assertEqual(
            kinds,
            [
                ("C0BRDFZPLHK", "1761410014.000100", "PLACE_ON_TITLED_WORKER"),
                ("C0BSBM78V1N", "1761410001.000100", "HAND_TO_COORDINATOR"),
                ("C0BSBM78V1N", "1761410003.000100", "HAND_TO_COORDINATOR"),
                ("C0BSBM78V1N", "1761410005.000100", "PLACE_ON_TITLED_WORKER"),
                ("C0BSBM78V1N", "1761410006.000100", "PLACE_ON_TITLED_WORKER"),
                ("C0BSBM78V1N", "1761410006.000200", "PEER_RECEIPT"),
                ("C0BSBM78V1N", "1761410008.000100", "BLOCKED_WAKE"),
                ("C0BSBM78V1N", "1761410009.000200", "HAND_TO_COORDINATOR"),
                ("C0BTD5804QK", "1761410013.000100", "HAND_TO_COORDINATOR"),
                ("C0BTD5804QK", "1761410013.000200", "PEER_RECEIPT"),
                ("C0C5FCK1F45", "1761410012.000100", "REFUSE_SECRET"),
                ("C0CCNK7JFAL", "1761410010.000100", "ACTION_NEEDED_RETURN"),
            ],
        )
        commission = decisions[1]
        self.assertEqual(commission["operation_id"], "hermes-wp5-shadow-001")
        self.assertEqual(commission["author"], "ChatGPT1")
        self.assertIn("bounded source note", commission["ask"])
        self.assertIn("do not merge", commission["limits"])
        self.assertFalse(commission["would_post"])
        thread = decisions[7]
        self.assertEqual(thread["operation_id"], "thread-op-009")
        self.assertEqual(thread["thread_ts"], "1761410009.000100")
        owed = decisions[11]
        self.assertEqual(owed["tasks"], ["rf-t01"])
        self.assertEqual(owed["decision"], "ACTION_NEEDED_RETURN")

    def test_duplicate_ts_is_one_decision(self):
        message = {
            "channel": "C0BSBM78V1N",
            "ts": "1761410030.000100",
            "user": "U0BRETDUAS2",
            "text": "<@U0BTCHX8HMF> DIRECT_TARGETED\noperation_id: dup-030",
        }
        seen: set[str] = set()
        first = scan([message, dict(message)], channels=("C0BSBM78V1N",), include_returns=False, ledger=[], roster=default_roster(), seen=seen)
        second = scan([message], channels=("C0BSBM78V1N",), include_returns=False, ledger=[], roster=default_roster(), seen=seen)
        self.assertEqual(len(first), 1)
        self.assertEqual(second, [])
        self.assertEqual(first[0]["operation_id"], "dup-030")

    def test_own_posts_and_other_seats_are_ignored(self):
        texts = " ".join(item["text"] for item in self.messages)
        self.assertIn("self-echo-003", texts)
        self.assertIn("other-seat-004", texts)
        decisions = scan(
            self.messages,
            channels=("C0BSBM78V1N",),
            include_returns=False,
            ledger=self.ledger,
            roster=self.roster,
            seen=set(),
        )
        blob = " ".join(json_blob(item) for item in decisions)
        self.assertIn("self-echo-003", blob)
        self.assertNotIn("other-seat-004", blob)
        self.assertNotIn("U0OTHERSEAT1", blob)
        echo = next(item for item in decisions if item.get("operation_id") == "self-echo-003")
        self.assertEqual(echo["author"], "Grok Secretary")
        self.assertNotEqual(echo["author"], "self")
        own = roster_with(self_user_id="UHERMESSELF1", other_seats=("U0OTHERSEAT1",))
        own_message = {
            "channel": "C0BSBM78V1N",
            "ts": "1761410060.000100",
            "user": "UHERMESSELF1",
            "text": "<@U0BTCHX8HMF> TO: Grok Secretary\noperation_id: own-loop-060",
        }
        self.assertIsNone(classify(
            own_message, messages=[own_message], ledger=[], roster=own, include_returns=False,
        ))
        sibling = roster_with(self_user_id="UHERMESSELF1", sibling_ids=("USIBLING001",))
        sibling_message = {
            "channel": "C0BSBM78V1N",
            "ts": "1761410061.000100",
            "user": "USIBLING001",
            "text": "<@U0BTCHX8HMF> TO: Grok Secretary\noperation_id: sibling-061",
        }
        found = classify(
            sibling_message, messages=[sibling_message], ledger=[], roster=sibling, include_returns=False,
        )
        self.assertEqual(found["decision"], "HAND_TO_COORDINATOR")
        self.assertFalse(sibling.is_self("USIBLING001"))

    def test_acked_placement_and_acked_commission_stay_quiet(self):
        decisions = scan(
            self.messages,
            channels=("C0BSBM78V1N", "C0BTD5804QK"),
            include_returns=False,
            ledger=[],
            roster=self.roster,
            seen=set(),
        )
        ids = {item["ts"] for item in decisions}
        self.assertIn("1761410006.000100", ids)
        self.assertIn("1761410013.000100", ids)
        receipts = [item for item in decisions if item["decision"] == "PEER_RECEIPT"]
        self.assertEqual({item["ts"] for item in receipts}, {"1761410006.000200", "1761410013.000200"})
        self.assertTrue(all(item["author"] == "Grok Secretary" for item in receipts))
        own = roster_with(self_user_id="UHERMESSELF1", other_seats=("U0OTHERSEAT1",))
        suppressed = scan(
            self.messages + [{
                "channel": "C0BSBM78V1N",
                "ts": "1761410005.000900",
                "thread_ts": "1761410005.000100",
                "user": "UHERMESSELF1",
                "text": "ACK own receipt",
            }],
            channels=("C0BSBM78V1N",),
            include_returns=False,
            ledger=[],
            roster=own,
            seen=set(),
        )
        self.assertNotIn("1761410005.000100", {item["ts"] for item in suppressed})

    def test_closed_ledger_row_does_not_match(self):
        decisions = scan(
            self.messages,
            channels=(),
            include_returns=True,
            ledger=self.ledger,
            roster=self.roster,
            seen=set(),
        )
        self.assertEqual([item["ts"] for item in decisions], ["1761410010.000100"])
        self.assertNotIn("rf-t02", decisions[0]["tasks"])

    def test_unresolved_chris_id_is_not_guessed_from_display_name(self):
        message = {
            "channel": "C0BSBM78V1N",
            "ts": "1761410040.000100",
            "user": "UNOTCHRIS01",
            "text": "Chris says TO: Grok Secretary\noperation_id: not-chris",
        }
        missed = classify(message, messages=[message], ledger=[], roster=default_roster(), include_returns=False)
        self.assertIsNone(missed)
        registered = roster_with(chris_user_id="UNOTCHRIS01")
        found = classify(message, messages=[message], ledger=[], roster=registered, include_returns=False)
        self.assertEqual(found["decision"], "HAND_TO_COORDINATOR")
        self.assertEqual(found["author"], "Chris")

    def test_dot_bot_requires_an_explicit_id(self):
        message = {
            "channel": "C0CBC6AEAQZ",
            "ts": "1761410041.000100",
            "user": "UDOTBOT0001",
            "text": "TO: Grok Secretary\noperation_id: dot-041",
        }
        self.assertIsNone(classify(message, messages=[message], ledger=[], roster=default_roster(), include_returns=False))
        found = classify(
            message,
            messages=[message],
            ledger=[],
            roster=roster_with(dot_user_ids=("UDOTBOT0001",)),
            include_returns=False,
        )
        self.assertEqual(found["author"], "Dot1")

    def test_status_only_blocked_thread_is_quiet_and_real_blocked_is_not(self):
        quiet = {
            "channel": "C0BSBM78V1N",
            "ts": "1761410042.000100",
            "user": "U0C59APBUN4",
            "text": "status-only watcher update",
        }
        real = {
            "channel": "C0BSBM78V1N",
            "ts": "1761410043.000100",
            "user": "U0C59APBUN4",
            "text": "DECISION_REQUEST HOLD-FOR-SOL",
        }
        negated = {
            "channel": "C0BSBM78V1N",
            "ts": "1761410044.000100",
            "user": "U0C59APBUN4",
            "text": "not BLOCKED, continuing",
        }
        self.assertIsNone(classify(quiet, messages=[quiet], ledger=[], roster=default_roster(), include_returns=False))
        self.assertIsNone(classify(negated, messages=[negated], ledger=[], roster=default_roster(), include_returns=False))
        found = classify(real, messages=[real], ledger=[], roster=default_roster(), include_returns=False)
        self.assertEqual(found["decision"], "BLOCKED_WAKE")

    def test_secret_text_is_not_copied_into_the_decision(self):
        message = {
            "channel": "C0C5FCK1F45",
            "ts": "1761410012.000100",
            "user": "U0BRETDUAS2",
            "text": "TO: Grok Secretary\ntoken: xoxb-not-a-real-token",
        }
        decision = classify(message, messages=[message], ledger=[], roster=default_roster(), include_returns=False)
        blob = json_blob(decision)
        self.assertEqual(decision["decision"], "REFUSE_SECRET")
        self.assertIsNone(decision["ask"])
        self.assertNotIn("xoxb-not-a-real-token", blob)
        self.assertNotIn("secret-012", blob)


def json_blob(decision: dict) -> str:
    return " ".join(str(value) for value in decision.values())


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from detect import classify
from roster import (
    RosterConfigError,
    authorized_post_room_ids,
    default_roster,
    load_roster_config,
    roster_from_mapping,
    watched_channel_ids,
)


class RosterConfig(unittest.TestCase):
    def test_shipped_config_fails_closed_on_the_unset_chris_slot(self):
        data = load_roster_config()
        self.assertIn("CHRIS_SLACK_USER_ID", data)
        self.assertIsNone(data["CHRIS_SLACK_USER_ID"])
        roster = default_roster()
        self.assertNotIn("Chris", roster.authors.values())
        self.assertEqual(roster.role("UNOTCHRIS01"), "other_seat")
        self.assertIsNone(roster.author_name("UNOTCHRIS01"))
        self.assertEqual(roster.secretary_user_id, "U0BTCHX8HMF")
        self.assertEqual(roster.role("U0BTCHX8HMF"), "self")
        self.assertEqual(roster.author_name("U0C5L14LT7G"), "ChatGPT2")
        self.assertEqual(roster.author_name("U0BSB73JWNL"), "ChatGPT2")

    def test_ids_live_in_the_config_file_not_constants(self):
        text = (ROOT / "constants.py").read_text(encoding="utf-8")
        for token in ("U0BTCHX8HMF", "U0C5L14LT7G", "C0CBC6AEAQZ", "CHRIS_SLACK_USER_ID"):
            self.assertNotIn(token, text)

    def test_missing_chris_slot_and_malformed_values_fail_closed(self):
        data = dict(load_roster_config())
        missing = dict(data)
        del missing["CHRIS_SLACK_USER_ID"]
        with self.assertRaises(RosterConfigError):
            roster_from_mapping(missing)
        blank = dict(data)
        blank["CHRIS_SLACK_USER_ID"] = "  "
        self.assertNotIn("Chris", roster_from_mapping(blank).authors.values())
        for bad in ("chris", "not-a-user", 12):
            broken = dict(data)
            broken["CHRIS_SLACK_USER_ID"] = bad
            with self.subTest(bad=bad):
                with self.assertRaises(RosterConfigError):
                    roster_from_mapping(broken)
        collision = dict(data)
        collision["CHRIS_SLACK_USER_ID"] = "U0BRETDUAS2"
        with self.assertRaises(RosterConfigError):
            roster_from_mapping(collision)

    def test_a_configured_chris_id_admits_only_that_user(self):
        data = dict(load_roster_config())
        data["CHRIS_SLACK_USER_ID"] = "UCHRIS00001"
        roster = roster_from_mapping(data)
        self.assertEqual(roster.author_name("UCHRIS00001"), "Chris")
        self.assertIsNone(roster.author_name("UNOTCHRIS01"))

    def test_watched_channels_and_the_two_post_rooms(self):
        self.assertEqual(
            watched_channel_ids(),
            (
                "C0BSBM78V1N",
                "C0BTD5804QK",
                "C0BRDFZPLHK",
                "C0CCNK7JFAL",
                "C0CBC6AEAQZ",
                "C0C5FCK1F45",
            ),
        )
        self.assertEqual(authorized_post_room_ids(), ("C0CBC6AEAQZ", "C0C5FCK1F45"))

    def test_chatgpt2_bot_user_can_commission(self):
        message = {
            "channel": "C0BSBM78V1N",
            "ts": "1761410050.000100",
            "user": "U0C5L14LT7G",
            "text": "TO: Grok Secretary\noperation_id: bot-050",
        }
        found = classify(
            message,
            messages=[message],
            ledger=[],
            roster=default_roster(),
            include_returns=False,
        )
        self.assertEqual(found["author"], "ChatGPT2")
        self.assertEqual(found["decision"], "HAND_TO_COORDINATOR")
        self.assertFalse(found["would_post"])


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from relay_mux import (  # noqa: E402
    RelayMuxRefusal,
    attribution_for,
    override_role,
    plan,
    route_for_channel,
)
import relay_mux  # noqa: E402
from roster import RosterConfigError, default_roster, load_roster_config  # noqa: E402

BOT_ID = "U0BT71H4FQE"
DOTS_ROOM = "C0CBC6AEAQZ"  # dotsandgroksecretary
META_ROOM = "C0C5FCK1F45"  # metaceo
DISPATCH_ROOM = "C0BSBM78V1N"  # agent-dispatch: watched but not a post room
DM_ID = "D0RELAYTEST"
UNKNOWN_ROOM = "C0UNROUTED9"


class RosterCollapseTest(unittest.TestCase):
    def test_roster_carries_single_relay_unit(self):
        config = load_roster_config()
        rows = config["hermes_agents"]
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["name"], "hermes-mmrelay")
        self.assertEqual(row["unit"], "hermes-runtime-mmrelay.service")
        self.assertEqual(row["secrets_file"], "mmrelay.secrets.env")
        self.assertEqual(row["self_user_id_env"], "HERMES_SLACK_BOT_USER_ID")
        self.assertEqual(row["bot_token_env"], "HERMES_SLACK_BOT_TOKEN")
        self.assertEqual(config["sibling_hermes_agent_ids"], [])

    def test_default_roster_accepts_single_unit(self):
        roster = default_roster(environ={"HERMES_SLACK_BOT_USER_ID": BOT_ID})
        self.assertEqual(roster.self_user_id, BOT_ID)

    def test_identity_guard_still_fails_closed(self):
        with self.assertRaises(RosterConfigError):
            default_roster(environ={"HERMES_SLACK_BOT_USER_ID": "U0BRET6191C"})  # Chris
        with self.assertRaises(RosterConfigError):
            default_roster(environ={"HERMES_SLACK_BOT_USER_ID": "U0BTCHX8HMF"})  # Grok peer


class RoutingTest(unittest.TestCase):
    def test_dm_routes_to_secretary(self):
        self.assertEqual(route_for_channel(DM_ID), "mmsecretary")

    def test_post_rooms_route(self):
        self.assertEqual(route_for_channel(DOTS_ROOM), "mmsecretary")
        self.assertEqual(route_for_channel(META_ROOM), "mmmeta")

    def test_watched_but_unrouted_surface_refuses(self):
        with self.assertRaises(RelayMuxRefusal) as caught:
            route_for_channel(DISPATCH_ROOM)
        self.assertEqual(caught.exception.code, "unrouted-surface")

    def test_unknown_surface_refuses(self):
        with self.assertRaises(RelayMuxRefusal):
            route_for_channel(UNKNOWN_ROOM)


class OverrideTest(unittest.TestCase):
    def test_mentioned_secretary_handle_wins(self):
        text = f"<@{BOT_ID}> Secretary, brief the exec room"
        self.assertEqual(override_role(text, bot_user_id=BOT_ID), "mmsecretary")

    def test_mentioned_meta_ceo_handle_wins(self):
        text = f"<@{BOT_ID}> Meta-CEO decision needed"
        self.assertEqual(override_role(text, bot_user_id=BOT_ID), "mmmeta")

    def test_no_mention_no_override(self):
        self.assertIsNone(override_role("secretary please", bot_user_id=BOT_ID))
        self.assertIsNone(override_role(f"<@{BOT_ID}> ping", bot_user_id=BOT_ID))

    def test_both_handles_refuse(self):
        text = f"<@{BOT_ID}> secretary and meta-ceo both"
        with self.assertRaises(RelayMuxRefusal) as caught:
            override_role(text, bot_user_id=BOT_ID)
        self.assertEqual(caught.exception.code, "ambiguous-role")


class AttributionTest(unittest.TestCase):
    def test_customize_kwargs_per_role(self):
        self.assertEqual(
            attribution_for("mmsecretary", customize=True),
            {"username": "Mastermind Secretary", "icon_emoji": ":scroll:"},
        )
        self.assertEqual(
            attribution_for("mmmeta", customize=True),
            {"username": "Meta-CEO", "icon_emoji": ":crown:"},
        )

    def test_fallback_is_bold_header_text(self):
        self.assertEqual(attribution_for("mmsecretary", customize=False), {})
        result = plan(DOTS_ROOM, "Overnight digest ready.", bot_user_id=BOT_ID, customize=False)
        self.assertTrue(result.text.startswith("*Secretary ·* "))
        result = plan(META_ROOM, "Decided.", bot_user_id=BOT_ID, customize=False)
        self.assertTrue(result.text.startswith("*Meta-CEO ·* "))

    def test_unknown_role_refuses(self):
        with self.assertRaises(RelayMuxRefusal):
            attribution_for("grok")


class PlanTest(unittest.TestCase):
    def test_plan_as_single_bot_identity(self):
        result = plan(DOTS_ROOM, "Overnight digest ready.", bot_user_id=BOT_ID)
        self.assertEqual(result.role, "mmsecretary")
        self.assertEqual(result.channel_id, DOTS_ROOM)
        self.assertEqual(result.bot_user_id, BOT_ID)
        self.assertEqual(result.text, "Overnight digest ready.")
        self.assertEqual(result.attribution["username"], "Mastermind Secretary")

    def test_override_redirects_route(self):
        text = f"<@{BOT_ID}> Meta-CEO, ack the exec room"
        result = plan(DOTS_ROOM, text, bot_user_id=BOT_ID)
        self.assertEqual(result.role, "mmmeta")

    def test_plan_refuses_human_identity(self):
        with self.assertRaises(RelayMuxRefusal) as caught:
            plan(DOTS_ROOM, "Never as Chris.", bot_user_id="U0BRET6191C")
        self.assertEqual(caught.exception.code, "identity-collision")

    def test_plan_refuses_bad_inputs(self):
        for channel, text, bot in (
            (DOTS_ROOM, "", BOT_ID),
            (DOTS_ROOM, "   ", BOT_ID),
            ("not-a-channel", "x", BOT_ID),
            (DOTS_ROOM, "x", "xoxb-not-a-user"),
            (DISPATCH_ROOM, "x", BOT_ID),
        ):
            with self.assertRaises(RelayMuxRefusal):
                plan(channel, text, bot_user_id=bot)

    def test_plan_carries_no_credential_and_module_writes_nothing(self):
        result = plan(META_ROOM, "Result staged.", bot_user_id=BOT_ID)
        self.assertNotIn("token", vars(result))
        source = Path(relay_mux.__file__).read_text(encoding="utf-8")
        for banned in ("chat_postMessage", "chat_update", "files_upload", "xoxb-"):
            self.assertNotIn(banned, source)


if __name__ == "__main__":
    unittest.main()

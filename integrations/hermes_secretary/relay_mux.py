"""Single-identity Slack relay mux for the Executive Relay bridge.

One Slack app (Executive Relay) carries ONE bot identity and one roster unit
(``hermes-mmrelay``) for both logical roles (``mmsecretary``, ``mmmeta``).
The roster's fail-closed identity guard stays the only authority on who
"self" is: this module reuses it instead of adding identity rules.

This module PLANS a delivery. It maps a Slack surface to the logical role
and the attribution a write-capable client would carry under
``chat:write.customize``. It is not a Slack client, loads no token, and
calls nothing. Shadow mode and the read-only client remain the only live
surfaces until the separate Chairman cutover grant.

Routing (DEC-SLACK-EXECUTIVE-RELAY-BRIDGE): DMs and the secretary post room
(``dotsandgroksecretary``) route to ``mmsecretary``; the exec post room
(``metaceo``) routes to ``mmmeta``; an explicit role handle in a message
that @-mentions the bot overrides the surface default. Every other surface
refuses — the mux never widens delivery. Channel ids resolve through the
roster, never through code constants.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from roster import RosterConfigError, channel_names, default_roster

# Mirrors native_dialogue_consumer.ROLES; kept local so this module and its
# tests do not depend on the session bridge.
LOGICAL_ROLES = frozenset(("mmsecretary", "mmmeta"))

_DM = re.compile(r"\AD[A-Z0-9]{8,31}\Z")
_BOT = re.compile(r"\AU[A-Z0-9]{8,31}\Z")

_ROLE_HANDLES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("mmsecretary", re.compile(r"(?i)\bsecretary\b")),
    ("mmmeta", re.compile(r"(?i)\bmeta[- ]?ceo\b")),
)

ATTRIBUTION: dict[str, dict[str, str]] = {
    "mmsecretary": {"username": "Mastermind Secretary", "icon_emoji": ":scroll:"},
    "mmmeta": {"username": "Meta-CEO", "icon_emoji": ":crown:"},
}

HEADER_PREFIX: dict[str, str] = {
    "mmsecretary": "*Secretary ·*",
    "mmmeta": "*Meta-CEO ·*",
}


class RelayMuxRefusal(RuntimeError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class RelayPlan:
    role: str
    channel_id: str
    bot_user_id: str
    text: str
    attribution: dict[str, str] = field(default_factory=dict)


def route_for_channel(channel_id: str) -> str:
    """Resolve the logical role for a surface. Anything unrouted refuses."""
    if isinstance(channel_id, str) and _DM.fullmatch(channel_id):
        return "mmsecretary"
    name = channel_names().get(channel_id)
    if name == "dotsandgroksecretary":
        return "mmsecretary"
    if name == "metaceo":
        return "mmmeta"
    raise RelayMuxRefusal("unrouted-surface")


def override_role(text: str, *, bot_user_id: str) -> str | None:
    """Explicit role handle wins, but only inside a bot @-mention."""
    if not isinstance(text, str) or f"<@{bot_user_id}>" not in text:
        return None
    found = [role for role, pattern in _ROLE_HANDLES if pattern.search(text)]
    if not found:
        return None
    if len(found) > 1:
        raise RelayMuxRefusal("ambiguous-role")
    return found[0]


def attribution_for(role: str, *, customize: bool = True) -> dict[str, str]:
    if role not in LOGICAL_ROLES:
        raise RelayMuxRefusal("unknown-role")
    return dict(ATTRIBUTION[role]) if customize else {}


def plan(
    channel_id: str,
    text: str,
    *,
    bot_user_id: str,
    customize: bool = True,
) -> RelayPlan:
    """Plan one outbound delivery as the single bot identity.

    The plan is data only. Carrying it out needs the Chairman cutover grant
    and a write-capable client that does not exist in this repo.
    """
    if not isinstance(text, str) or not text.strip():
        raise RelayMuxRefusal("empty-text")
    if not isinstance(bot_user_id, str) or _BOT.fullmatch(bot_user_id) is None:
        raise RelayMuxRefusal("bad-bot-id")
    if not isinstance(channel_id, str) or not (_DM.fullmatch(channel_id) or re.fullmatch(r"[CG][A-Z0-9]{8,31}", channel_id)):
        raise RelayMuxRefusal("bad-channel")
    # Reuse the roster's fail-closed guard: a bot id that collides with any
    # configured human, commissioner, peer or sibling must never plan a post.
    try:
        default_roster(environ={"HERMES_SLACK_BOT_USER_ID": bot_user_id})
    except RosterConfigError:
        raise RelayMuxRefusal("identity-collision") from None
    role = override_role(text, bot_user_id=bot_user_id) or route_for_channel(channel_id)
    final_text = text if customize else f"{HEADER_PREFIX[role]} {text}"
    return RelayPlan(
        role=role,
        channel_id=channel_id,
        bot_user_id=bot_user_id,
        text=final_text,
        attribution=attribution_for(role, customize=customize),
    )


MODULE_PATH = Path(__file__).resolve()

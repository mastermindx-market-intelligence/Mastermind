"""Roster and room config. Slack ids live in roster.json, not in code constants."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping


CONFIG_PATH = Path(__file__).with_name("roster.json")
_USER = re.compile(r"^U[A-Z0-9]{6,32}$")
_CHANNEL = re.compile(r"^[CG][A-Z0-9]{8,31}$")


class RosterConfigError(ValueError):
    pass


@dataclass(frozen=True)
class Roster:
    authors: Mapping[str, str]
    grok_secretary_user_id: str
    grok_secretary_name: str = "Grok Secretary"
    self_user_id: str | None = None
    sibling_ids: frozenset[str] = field(default_factory=frozenset)
    sibling_names: Mapping[str, str] = field(default_factory=dict)
    other_seats: frozenset[str] = field(default_factory=frozenset)

    def role(self, user_id: str) -> str:
        if self.self_user_id is not None and user_id == self.self_user_id:
            return "self"
        if user_id == self.grok_secretary_user_id:
            return "peer"
        if user_id in self.sibling_ids:
            return "sibling"
        if user_id in self.other_seats:
            return "other_seat"
        if user_id in self.authors:
            return "allowed"
        return "other_seat"

    def author_name(self, user_id: str) -> str | None:
        if user_id == self.grok_secretary_user_id:
            return self.grok_secretary_name
        if user_id in self.sibling_names:
            return self.sibling_names[user_id]
        return self.authors.get(user_id)

    def is_self(self, user_id: str) -> bool:
        return self.role(user_id) == "self"

    def may_address(self, user_id: str) -> bool:
        """Thread address book. Own bot id is never addressable. Grok is."""

        if self.is_self(user_id):
            return False
        return user_id == self.grok_secretary_user_id or user_id in self.sibling_ids


def load_roster_config(path: Path | None = None) -> dict:
    target = path or CONFIG_PATH
    data = json.loads(target.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise RosterConfigError("roster config must be an object")
    _require_shape(data)
    return data


def roster_from_mapping(
    data: Mapping[str, object],
    *,
    environ: Mapping[str, str] | None = None,
    self_user_id: str | None = None,
    sibling_ids: tuple[str, ...] | None = None,
) -> Roster:
    """Build a roster. Self is this agent's HERMES_SLACK_BOT_USER_ID only."""

    if "CHRIS_SLACK_USER_ID" not in data:
        raise RosterConfigError("CHRIS_SLACK_USER_ID slot is required")
    authors = _commissioners(data)
    peer = _grok_peer(data)
    chris = _chris_id(data["CHRIS_SLACK_USER_ID"])
    if chris in authors or chris == peer["user_id"]:
        raise RosterConfigError("CHRIS_SLACK_USER_ID collides with a configured user")
    chris_row = data.get("chris")
    if isinstance(chris_row, dict) and isinstance(chris_row.get("name"), str) and chris_row["name"].strip():
        authors[chris] = chris_row["name"].strip()
    else:
        authors[chris] = "Chris"
    own = self_user_id if self_user_id is not None else _self_from_env(environ)
    siblings = _siblings(data if sibling_ids is None else {"sibling_hermes_agent_ids": list(sibling_ids)})
    _reject_identity_collisions(own, siblings, authors, peer["user_id"], chris)
    return Roster(
        authors=authors,
        grok_secretary_user_id=peer["user_id"],
        grok_secretary_name=peer["name"],
        self_user_id=own,
        sibling_ids=frozenset(siblings),
    )


def default_roster(*, environ: Mapping[str, str] | None = None) -> Roster:
    return roster_from_mapping(load_roster_config(), environ=environ)


def roster_with(
    *,
    chris_user_id: str | None = None,
    dot_user_ids: tuple[str, ...] = (),
    other_seats: tuple[str, ...] = (),
    self_user_id: str | None = None,
    sibling_ids: tuple[str, ...] = (),
    environ: Mapping[str, str] | None = None,
) -> Roster:
    """Test and operator overlay. An omitted Chris id uses the config slot."""

    data = dict(load_roster_config())
    if chris_user_id is not None:
        data["CHRIS_SLACK_USER_ID"] = chris_user_id
        chris_row = dict(data.get("chris") or {})
        chris_row["user_id"] = chris_user_id
        chris_row.setdefault("name", "Chris")
        data["chris"] = chris_row
    if sibling_ids:
        data["sibling_hermes_agent_ids"] = list(sibling_ids)
    roster = roster_from_mapping(data, environ=environ, self_user_id=self_user_id)
    authors = dict(roster.authors)
    for index, dot_id in enumerate(dot_user_ids, start=1):
        if dot_id in authors or dot_id == roster.grok_secretary_user_id or dot_id == roster.self_user_id:
            raise RosterConfigError("dot user id collides with a configured user")
        authors[dot_id] = f"Dot{index}"
    overlap = set(other_seats) & set(authors)
    if (
        roster.grok_secretary_user_id in other_seats
        or roster.self_user_id in other_seats
        or overlap
        or set(other_seats) & set(roster.sibling_ids)
    ):
        raise RosterConfigError("other seats cannot also be allowed authors")
    return Roster(
        authors=authors,
        grok_secretary_user_id=roster.grok_secretary_user_id,
        grok_secretary_name=roster.grok_secretary_name,
        self_user_id=roster.self_user_id,
        sibling_ids=roster.sibling_ids,
        other_seats=frozenset(other_seats),
    )


def channel_names() -> dict[str, str]:
    return {row["id"]: row["name"] for row in load_roster_config()["watched_channels"]}


def watched_channel_ids() -> tuple[str, ...]:
    return tuple(row["id"] for row in load_roster_config()["watched_channels"])


def returns_channel_id() -> str:
    return _id_named("chatgpt-web-returns")


def agent_dispatch_id() -> str:
    return _id_named("agent-dispatch")


def original_room_ids() -> tuple[str, ...]:
    return tuple(load_roster_config()["original_rooms"])


def authorized_post_room_ids() -> tuple[str, ...]:
    return tuple(row["id"] for row in load_roster_config()["authorized_post_rooms"])


def authorized_reply_kinds() -> frozenset[str]:
    return frozenset(
        str(kind).upper() for kind in load_roster_config()["authorized_thread_replies"]
    )


def _id_named(name: str) -> str:
    for row in load_roster_config()["watched_channels"]:
        if row["name"] == name:
            return row["id"]
    raise RosterConfigError(f"watched channel {name} is not configured")


def _require_shape(data: Mapping[str, object]) -> None:
    if "CHRIS_SLACK_USER_ID" not in data:
        raise RosterConfigError("CHRIS_SLACK_USER_ID slot is required")
    peer = _grok_peer(data)
    chris = _chris_id(data["CHRIS_SLACK_USER_ID"])
    authors = _commissioners(data)
    _agents(data)
    siblings = _siblings(data)
    _reject_identity_collisions(None, siblings, authors, peer["user_id"], chris)
    watched = data.get("watched_channels")
    rooms = data.get("authorized_post_rooms")
    original = data.get("original_rooms")
    kinds = data.get("authorized_thread_replies")
    if not isinstance(watched, list) or not watched:
        raise RosterConfigError("watched_channels are required")
    if not isinstance(rooms, list) or len(rooms) != 2:
        raise RosterConfigError("exactly two authorized post rooms are required")
    if not isinstance(original, list) or len(original) != 3:
        raise RosterConfigError("original_rooms must be the three overnight rooms")
    if not isinstance(kinds, list) or not kinds:
        raise RosterConfigError("authorized_thread_replies are required")
    watched_ids = []
    for row in watched:
        if not isinstance(row, dict):
            raise RosterConfigError("watched channel is malformed")
        watched_ids.append(_channel(row.get("id"), "watched channel"))
    room_ids = []
    for row in rooms:
        if not isinstance(row, dict):
            raise RosterConfigError("authorized post room is malformed")
        room_ids.append(_channel(row.get("id"), "authorized post room"))
    if any(room_id not in watched_ids for room_id in room_ids):
        raise RosterConfigError("authorized post rooms must be watched channels")
    for room_id in original:
        if room_id not in watched_ids:
            raise RosterConfigError("original rooms must be watched channels")
    if _id_in(watched, "chatgpt-web-returns") is None or _id_in(watched, "agent-dispatch") is None:
        raise RosterConfigError("agent-dispatch and chatgpt-web-returns must be watched")
    if chris in authors or chris == peer["user_id"] or chris in siblings:
        raise RosterConfigError("CHRIS_SLACK_USER_ID collides with a configured user")
    chris_row = data.get("chris")
    if not isinstance(chris_row, dict) or chris_row.get("user_id") != chris:
        raise RosterConfigError("chris.user_id must match CHRIS_SLACK_USER_ID")
    email = chris_row.get("email")
    if not isinstance(email, str) or "@" not in email:
        raise RosterConfigError("chris.email is required")


def _id_in(rows: list, name: str) -> str | None:
    for row in rows:
        if isinstance(row, dict) and row.get("name") == name:
            return row.get("id")
    return None


def _commissioners(data: Mapping[str, object]) -> dict[str, str]:
    rows = data.get("commissioners")
    if not isinstance(rows, list) or not rows:
        raise RosterConfigError("commissioners are required")
    authors: dict[str, str] = {}
    for row in rows:
        if not isinstance(row, dict):
            raise RosterConfigError("commissioner is malformed")
        user_id = row.get("user_id")
        name = row.get("name")
        if not isinstance(user_id, str) or _USER.fullmatch(user_id) is None:
            raise RosterConfigError("commissioner user id fails closed")
        if not isinstance(name, str) or not name.strip():
            raise RosterConfigError("commissioner name is missing")
        if user_id in authors:
            raise RosterConfigError("commissioner user id collides")
        authors[user_id] = name
    return authors


def _grok_peer(data: Mapping[str, object]) -> dict[str, str]:
    rows = data.get("peers")
    if not isinstance(rows, list) or not rows:
        raise RosterConfigError("peers are required")
    found: dict[str, str] | None = None
    for row in rows:
        if not isinstance(row, dict):
            raise RosterConfigError("peer is malformed")
        user_id = row.get("user_id")
        name = row.get("name")
        if not isinstance(user_id, str) or _USER.fullmatch(user_id) is None:
            raise RosterConfigError("peer user id fails closed")
        if not isinstance(name, str) or not name.strip():
            raise RosterConfigError("peer name is missing")
        if name.strip() == "Grok Secretary":
            if found is not None:
                raise RosterConfigError("Grok Secretary is listed twice")
            found = {"user_id": user_id, "name": name.strip()}
    if found is None:
        raise RosterConfigError("Grok Secretary peer is required")
    return found


def _agents(data: Mapping[str, object]) -> list[dict]:
    rows = data.get("hermes_agents")
    if not isinstance(rows, list) or len(rows) < 2:
        raise RosterConfigError("hermes_agents require one entry per always-on unit")
    names: set[str] = set()
    units: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            raise RosterConfigError("hermes agent is malformed")
        name = row.get("name")
        unit = row.get("unit")
        secrets = row.get("secrets_file")
        if not isinstance(name, str) or not name.strip() or name in names:
            raise RosterConfigError("hermes agent name is missing or duplicated")
        if not isinstance(unit, str) or not unit.endswith(".service") or unit in units:
            raise RosterConfigError("hermes agent unit must be a distinct user service")
        if row.get("self_user_id_env") != "HERMES_SLACK_BOT_USER_ID":
            raise RosterConfigError("self is HERMES_SLACK_BOT_USER_ID per agent unit")
        if row.get("bot_token_env") != "HERMES_SLACK_BOT_TOKEN":
            raise RosterConfigError("bot token env is HERMES_SLACK_BOT_TOKEN per agent unit")
        if not isinstance(secrets, str) or not secrets.endswith(".secrets.env"):
            raise RosterConfigError("hermes agent secrets file is missing")
        names.add(name)
        units.add(unit)
    return rows


def _siblings(data: Mapping[str, object]) -> list[str]:
    rows = data.get("sibling_hermes_agent_ids")
    if not isinstance(rows, list):
        raise RosterConfigError("sibling_hermes_agent_ids must be a list")
    found: list[str] = []
    for user_id in rows:
        if not isinstance(user_id, str) or _USER.fullmatch(user_id) is None:
            raise RosterConfigError("sibling hermes agent id fails closed")
        if user_id in found:
            raise RosterConfigError("sibling hermes agent id is duplicated")
        found.append(user_id)
    return found


def _self_from_env(environ: Mapping[str, str] | None) -> str | None:
    if environ is None:
        return None
    value = environ.get("HERMES_SLACK_BOT_USER_ID")
    if value is None or str(value).strip() == "":
        return None
    if not isinstance(value, str) or _USER.fullmatch(value) is None:
        raise RosterConfigError("HERMES_SLACK_BOT_USER_ID fails closed")
    return value


def _reject_identity_collisions(
    own: str | None,
    siblings: list[str],
    authors: Mapping[str, str],
    grok_id: str,
    chris: str,
) -> None:
    if grok_id in siblings or grok_id in authors:
        raise RosterConfigError("Grok Secretary cannot be a Hermes agent or a commissioner")
    if own is not None and (own == grok_id or own == chris or own in authors or own in siblings):
        raise RosterConfigError("HERMES_SLACK_BOT_USER_ID collides with another identity")
    for user_id in siblings:
        if user_id == chris or user_id in authors:
            raise RosterConfigError("sibling hermes agent id collides with a configured user")


def _chris_id(value: object) -> str:
    if not isinstance(value, str) or _USER.fullmatch(value) is None:
        raise RosterConfigError("CHRIS_SLACK_USER_ID is required")
    return value


def _channel(value: object, label: str) -> str:
    if not isinstance(value, str) or _CHANNEL.fullmatch(value) is None:
        raise RosterConfigError(f"{label} fails closed")
    return value

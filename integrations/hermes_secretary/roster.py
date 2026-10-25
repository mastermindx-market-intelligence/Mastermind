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
    secretary_user_id: str
    other_seats: frozenset[str] = field(default_factory=frozenset)

    def role(self, user_id: str) -> str:
        if user_id == self.secretary_user_id:
            return "self"
        if user_id in self.other_seats:
            return "other_seat"
        if user_id in self.authors:
            return "allowed"
        return "other_seat"

    def author_name(self, user_id: str) -> str | None:
        if self.role(user_id) != "allowed":
            return None
        return self.authors[user_id]


def load_roster_config(path: Path | None = None) -> dict:
    target = path or CONFIG_PATH
    data = json.loads(target.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise RosterConfigError("roster config must be an object")
    _require_shape(data)
    return data


def roster_from_mapping(data: Mapping[str, object]) -> Roster:
    """Build a roster. An unset CHRIS_SLACK_USER_ID adds nobody."""

    if "CHRIS_SLACK_USER_ID" not in data:
        raise RosterConfigError("CHRIS_SLACK_USER_ID slot is required")
    authors = _commissioners(data)
    chris = _chris_id(data["CHRIS_SLACK_USER_ID"])
    if chris is not None:
        if chris in authors or chris == _secretary_id(data):
            raise RosterConfigError("CHRIS_SLACK_USER_ID collides with a configured user")
        authors[chris] = "Chris"
    return Roster(authors=authors, secretary_user_id=_secretary_id(data))


def default_roster() -> Roster:
    return roster_from_mapping(load_roster_config())


def roster_with(
    *,
    chris_user_id: str | None = None,
    dot_user_ids: tuple[str, ...] = (),
    other_seats: tuple[str, ...] = (),
) -> Roster:
    """Test and operator overlay. An omitted Chris id uses the config slot."""

    data = dict(load_roster_config())
    if chris_user_id is not None:
        data["CHRIS_SLACK_USER_ID"] = chris_user_id
    roster = roster_from_mapping(data)
    authors = dict(roster.authors)
    for index, dot_id in enumerate(dot_user_ids, start=1):
        if dot_id in authors or dot_id == roster.secretary_user_id:
            raise RosterConfigError("dot user id collides with a configured user")
        authors[dot_id] = f"Dot{index}"
    overlap = set(other_seats) & set(authors)
    if roster.secretary_user_id in other_seats or overlap:
        raise RosterConfigError("other seats cannot also be allowed authors")
    return Roster(
        authors=authors,
        secretary_user_id=roster.secretary_user_id,
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
    _secretary_id(data)
    _chris_id(data["CHRIS_SLACK_USER_ID"])
    authors = _commissioners(data)
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
    chris = _chris_id(data["CHRIS_SLACK_USER_ID"])
    if chris is not None and (chris in authors or chris == _secretary_id(data)):
        raise RosterConfigError("CHRIS_SLACK_USER_ID collides with a configured user")


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
        if user_id in authors or user_id == _secretary_id(data):
            raise RosterConfigError("commissioner user id collides")
        authors[user_id] = name
    return authors


def _secretary_id(data: Mapping[str, object]) -> str:
    user_id = data.get("secretary_user_id")
    if not isinstance(user_id, str) or _USER.fullmatch(user_id) is None:
        raise RosterConfigError("secretary_user_id fails closed")
    return user_id


def _chris_id(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, str) and value.strip() == "":
        return None
    if not isinstance(value, str) or _USER.fullmatch(value) is None:
        raise RosterConfigError("CHRIS_SLACK_USER_ID fails closed")
    return value


def _channel(value: object, label: str) -> str:
    if not isinstance(value, str) or _CHANNEL.fullmatch(value) is None:
        raise RosterConfigError(f"{label} fails closed")
    return value

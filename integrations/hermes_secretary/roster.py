"""Who may commission Grok Secretary, and whose traffic is ignored."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

from constants import KNOWN_AUTHORS, SECRETARY_USER_ID


@dataclass(frozen=True)
class Roster:
    authors: Mapping[str, str]
    other_seats: frozenset[str] = field(default_factory=frozenset)
    secretary_user_id: str = SECRETARY_USER_ID

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


def default_roster() -> Roster:
    """Snapshot roster. Chris and the Dot bots stay unresolved."""

    return Roster(authors=dict(KNOWN_AUTHORS))


def roster_with(
    *,
    chris_user_id: str | None = None,
    dot_user_ids: tuple[str, ...] = (),
    other_seats: tuple[str, ...] = (),
) -> Roster:
    authors = dict(KNOWN_AUTHORS)
    if chris_user_id:
        if chris_user_id in authors:
            raise ValueError("chris_user_id collides with a known author")
        authors[chris_user_id] = "Chris"
    for index, dot_id in enumerate(dot_user_ids, start=1):
        if dot_id in authors:
            raise ValueError("dot user id collides with a known author")
        authors[dot_id] = f"Dot{index}"
    overlap = set(other_seats) & set(authors)
    if overlap:
        raise ValueError("other seats cannot also be allowed authors")
    return Roster(authors=authors, other_seats=frozenset(other_seats))

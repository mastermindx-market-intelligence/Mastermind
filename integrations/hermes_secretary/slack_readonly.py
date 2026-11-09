"""Slack surface that can read history and thread replies, and nothing else."""

from __future__ import annotations

from typing import Mapping


class ReadOnlySlackError(RuntimeError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


_WRITE_PREFIXES = ("chat_", "files_", "reactions_", "pins_", "admin_", "usergroups_")
_WRITE_NAMES = frozenset(
    {
        "chat_postMessage",
        "chat_update",
        "chat_delete",
        "chat_postEphemeral",
        "chat_scheduleMessage",
        "conversations_invite",
        "conversations_kick",
        "files_upload",
        "reactions_add",
    }
)


class ReadOnlySlackClient:
    """In-memory stand-in for ``conversations.history`` and ``conversations.replies``.

    ``read_only`` is the marker ``assert_read_only_client`` requires. Adding a
    write method on a subclass fails that check before any call.
    """

    read_only = True

    def __init__(
        self,
        history: Mapping[str, list[dict]],
        replies: Mapping[tuple[str, str], list[dict]] | None = None,
    ) -> None:
        self._history = {channel: [dict(item) for item in rows] for channel, rows in history.items()}
        self._replies = {
            key: [dict(item) for item in rows] for key, rows in (replies or {}).items()
        }
        self.calls: list[tuple] = []

    def conversations_history(self, *, channel: str, limit: int = 200) -> list[dict]:
        self.calls.append(("conversations_history", channel, limit))
        return [dict(item) for item in self._history.get(channel, [])]

    def conversations_replies(self, *, channel: str, ts: str, limit: int = 200) -> list[dict]:
        self.calls.append(("conversations_replies", channel, ts, limit))
        return [dict(item) for item in self._replies.get((channel, ts), [])]


def assert_read_only_client(client: object) -> None:
    if getattr(type(client), "read_only", None) is not True:
        raise ReadOnlySlackError("SLACK_CLIENT_NOT_READ_ONLY")
    bad = [
        name
        for name in dir(type(client))
        if name in _WRITE_NAMES or name.startswith(_WRITE_PREFIXES)
    ]
    if bad:
        raise ReadOnlySlackError("SLACK_CLIENT_WRITE_SURFACE")

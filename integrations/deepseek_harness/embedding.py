"""Frame policy for the full DeepSeek app, bound to the existing sealed OS index.

This is presentation configuration only. It supplies no DSH authentication,
provider route, project authority or execution grant.
"""
from __future__ import annotations

from html.parser import HTMLParser
import re

_META_NAME = "mastermind-dsh-app"
_ORIGIN = re.compile(r"https://(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+mastermind-x\.com/")


def qualified_chat_origin(index: bytes) -> str | None:
    """Read at most one exact company HTTPS origin from hashed release bytes."""
    class Metadata(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=True)
            self.values = []

        def handle_starttag(self, tag, attrs):
            if tag != "meta":
                return
            names = [value for name, value in attrs if name == "name"]
            if not any(type(value) is str and value.casefold() == _META_NAME for value in names):
                return
            if len(names) != 1 or len(attrs) != 2 or {name for name, _ in attrs} != {"name", "content"}:
                raise ValueError("invalid DeepSeek application metadata")
            self.values.append(dict(attrs)["content"])

    parser = Metadata()
    parser.feed(index.decode("utf-8"))
    parser.close()
    if not parser.values:
        return None
    if len(parser.values) != 1:
        raise ValueError("duplicate DeepSeek application metadata")
    value = parser.values[0]
    if (type(value) is not str or not _ORIGIN.fullmatch(value)
            or value == "https://mcp.mastermind-x.com/" or len(value) > 2048):
        raise ValueError("DeepSeek requires a separate qualified company HTTPS origin")
    return value[:-1]

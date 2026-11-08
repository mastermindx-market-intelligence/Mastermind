import asyncio

import pytest

from integrations.deepseek_harness.embedding import qualified_chat_origin


def index(url):
    return ('<html><head><meta name="mastermind-dsh-app" content="' + url + '"></head></html>').encode()


@pytest.mark.parametrize("url", [
    "http://chat.mastermind-x.com/", "https://mcp.mastermind-x.com/",
    "https://chat.mastermind-x.com.evil.test/", "https://user@chat.mastermind-x.com/",
    "https://chat.mastermind-x.com/?token=x", "https://chat.mastermind-x.com/#x",
    "https://chat.mastermind-x.com/path/", "https://chat.mastermind-x.com:9443/",
    "https://a..mastermind-x.com/", "https://chat.mastermind-x.com/?",
])
def test_rejects_unqualified_frame_destinations(url):
    with pytest.raises(ValueError):
        qualified_chat_origin(index(url))


def test_metadata_is_optional_unique_and_closed():
    assert qualified_chat_origin(b"<html></html>") is None
    assert qualified_chat_origin(index("https://chat.mastermind-x.com/")) == "https://chat.mastermind-x.com"
    with pytest.raises(ValueError):
        qualified_chat_origin(index("https://chat.mastermind-x.com/") * 2)
    with pytest.raises(ValueError):
        qualified_chat_origin(b'<meta name="mastermind-dsh-app" content="https://chat.mastermind-x.com/" onclick="x">')


def test_sealed_static_owner_adds_only_the_exact_frame_origin():
    from integrations.executive_mcp.server import OsStaticApp

    async def response(app, path):
        sent = []
        async def send(message):
            sent.append(message)
        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}
        await app({"type": "http", "method": "GET", "path": path, "raw_path": path.encode(),
                   "query_string": b""}, receive, send)
        return dict((key.decode(), value.decode()) for key, value in sent[0]["headers"])

    app = OsStaticApp({
        "/os/": (index("https://chat.mastermind-x.com/"), "text/html; charset=utf-8"),
        "/os/assets/index-code.js": (b"export {};", "text/javascript; charset=utf-8"),
        "/os/assets/index-style.css": (b"body{}", "text/css; charset=utf-8"),
    })
    shell = asyncio.run(response(app, "/os/"))["content-security-policy"]
    callback = asyncio.run(response(app, "/os/auth/callback"))["content-security-policy"]
    def directives(policy):
        return {tokens[0]: tokens[1:] for row in policy.split(";") if (tokens := row.split())}
    shell_policy, callback_policy = directives(shell), directives(callback)
    existing = ["'self'", "https://dev-eo0jf8us5mup7wd5.us.auth0.com"]
    assert shell_policy["frame-src"] == [*existing, "https://chat.mastermind-x.com"]
    assert shell_policy["connect-src"] == existing
    assert callback_policy["frame-src"] == existing
    assert callback_policy["connect-src"] == existing
    assert shell_policy["frame-ancestors"] == ["'none'"]
    assert callback_policy["frame-ancestors"] == ["'self'"]

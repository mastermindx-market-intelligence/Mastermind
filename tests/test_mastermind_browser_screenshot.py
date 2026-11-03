from __future__ import annotations

import asyncio
import base64
import hashlib
import io
import json
import random

import httpx
import pytest
from PIL import Image

from integrations.mastermind_browser_plugin.facade import BrowserFacade
from integrations.mastermind_browser_plugin.screenshot import (
    MAX_ENCODED_IMAGE_BYTES,
    separate_screenshot,
)
from integrations.mastermind_browser_plugin.server import create_http_app
from tests.test_mastermind_browser_service import Owner


def _image(format="PNG", width=32, height=24, *, noise=False):
    pixels = (
        random.Random(42).randbytes(width * height * 3)
        if noise else bytes([40, 80, 120]) * width * height
    )
    buffer = io.BytesIO()
    Image.frombytes("RGB", (width, height), pixels).save(buffer, format=format)
    return buffer.getvalue()


def _result(raw, mime="image/png"):
    return {
        "content": [
            {"type": "text", "text": "Current viewport"},
            {"type": "image", "mimeType": mime, "data": base64.b64encode(raw).decode("ascii")},
        ],
        "isError": False,
    }


def test_screenshot_keeps_native_bytes_out_of_structured_result():
    raw = _image()
    data, images = separate_screenshot(_result(raw))
    metadata = data["content"][1]
    assert metadata["sha256"] == hashlib.sha256(raw).hexdigest()
    assert (metadata["width"], metadata["height"]) == (32, 24)
    assert metadata["byte_length"] == len(raw)
    assert "data" not in metadata
    assert base64.b64decode(images[0].data) == raw


@pytest.mark.parametrize("payload", [
    _result(b"valid base64, not an image"),
    _result(_image(), "image/jpeg"),
    _result(_image("JPEG")[:200], "image/jpeg"),
    _result(_image(), "image/svg+xml"),
    _result(_image(width=8193, height=1)),
    {"content": [{"type": "image", "mimeType": "image/png", "data": "not!base64"}]},
    {"content": [{"type": "image", "mimeType": "image/png", "data": "a" * (MAX_ENCODED_IMAGE_BYTES + 1)}]},
    {"content": [{"type": "resource_link", "uri": "file:///private/screenshot.png"}]},
    {"content": [{"type": "text", "text": "No screenshot"}]},
    {**_result(_image()), "isError": True},
    {"content": [_result(_image())["content"][1]] * 2},
])
def test_malformed_corrupt_oversize_or_nonimage_results_refuse(payload):
    with pytest.raises(ValueError):
        separate_screenshot(payload)


def test_screenshot_facade_retains_text_budget_and_no_effect():
    class ScreenshotOwner(Owner):
        async def browser_screenshot(self, caller, args):
            return {**_result(_image()), "debug": "x" * 70_000}

    result = asyncio.run(
        BrowserFacade(owner=ScreenshotOwner(), caller_resolver=lambda: "alice").call(
            "browser_screenshot", {"tab_ref": "tab-1"}
        )
    )
    assert result["code"] == "OWNER_RESULT_INVALID"
    assert result["effect"] == "NOT_APPLIED"


def test_http_mcp_delivers_large_valid_screenshot_as_native_image_once():
    raw = _image(width=400, height=300, noise=True)
    assert len(raw) > 65_536
    seen = []

    class ScreenshotOwner(Owner):
        async def browser_screenshot(self, caller, args):
            seen.append((caller, args))
            return _result(raw)

    app = create_http_app(
        owner=ScreenshotOwner(),
        authenticate=lambda request: "alice" if request.headers.get("x-fixture") == "alice" else None,
        auth_challenge="Bearer fixture",
        allowed_hosts=["browser.test"],
    )

    async def exercise():
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="https://browser.test"
            ) as client:
                response = await client.post(
                    "/browser-fabric",
                    headers={
                        "Accept": "application/json, text/event-stream",
                        "x-fixture": "alice",
                    },
                    json={
                        "jsonrpc": "2.0", "id": 1, "method": "tools/call",
                        "params": {"name": "browser_screenshot", "arguments": {"tab_ref": "tab-1"}},
                    },
                )
                assert response.status_code == 200
                result = response.json()["result"]
                assert result["isError"] is False
                images = [block for block in result["content"] if block["type"] == "image"]
                assert len(images) == 1
                assert base64.b64decode(images[0]["data"]) == raw
                assert images[0]["mimeType"] == "image/png"
                assert len(result["content"][0]["text"].encode()) < 65_536
                assert len(json.dumps(result["structuredContent"]).encode()) < 65_536
                assert images[0]["data"] not in result["content"][0]["text"]
                assert seen == [("alice", {"tab_ref": "tab-1"})]

    asyncio.run(exercise())

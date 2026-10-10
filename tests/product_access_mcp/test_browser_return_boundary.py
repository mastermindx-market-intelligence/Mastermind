"""Existing Browser MCP return qualification. No browser or real screenshot is used.

The image is a one-pixel fixture. The strict xfail is an explicitly unresolved
incumbent integrity gate, not a passed negative case or permission to install.
"""
from __future__ import annotations

import base64
import copy
import hashlib
import struct
import unittest
import zlib
from unittest.mock import patch

import pytest

from tests import test_workbench_browser_app as existing


def fixture_png() -> bytes:
    def chunk(name: bytes, value: bytes) -> bytes:
        return struct.pack(">I", len(value)) + name + value + struct.pack(">I", zlib.crc32(name + value) & 0xffffffff)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(b"\0\0\0\0")) + chunk(b"IEND", b"")


class BrowserNativeReturnTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.fixture = existing.WorkbenchBrowserAppTests()
        self.png = fixture_png()
        self.native = {"content": [{"type": "image", "mimeType": "image/png", "data": base64.b64encode(self.png).decode("ascii")}], "isError": False}
        self.mode = "normal"
        original = existing.create_authenticated_browser_server
        async def read_tool(caller, browser_ref, tool, arguments):
            self.fixture.calls.append(("read_tool", caller, browser_ref, tool, dict(arguments)))
            if self.mode == "expire":
                self.fixture.clock += 7200
            return copy.deepcopy(self.native)
        def compose(**kwargs):
            return original(**{**kwargs, "read_tool": read_tool})
        with patch.object(existing, "create_authenticated_browser_server", side_effect=compose):
            await self.fixture.asyncSetUp()

    async def asyncTearDown(self):
        await self.fixture.asyncTearDown()

    async def screenshot(self):
        # This is the existing SDK route with a fixture owner port, NOT a page capture.
        return await self.fixture.tool_call("browser_take_screenshot", {"browser_ref": self.fixture.browser_ref, "type": "png", "scale": "css"})

    async def test_existing_sdk_returns_exact_native_png_without_artifact_plugin(self):
        result = await self.screenshot()
        self.assertFalse(result.get("isError", False), result)
        item = result["content"][0]
        self.assertEqual((item["type"], item["mimeType"]), ("image", "image/png"))
        decoded = base64.b64decode(item["data"], validate=True)
        self.assertEqual(decoded, self.png)
        self.assertEqual(hashlib.sha256(decoded).digest(), hashlib.sha256(self.png).digest())
        self.assertEqual(len(self.fixture.calls), 1)

    async def test_authorization_expiry_during_capture_discards_native_image(self):
        self.mode = "expire"
        result = await self.screenshot()
        self.assertEqual(len(self.fixture.calls), 1, "The native producer must be reached before post-read expiry is tested")
        self.assertTrue(result["isError"], result)
        self.assertFalse(any(item["type"] == "image" for item in result["content"]))
        self.assertNotIn(self.native["content"][0]["data"], str(result))

    @pytest.mark.xfail(strict=True, reason="Existing Browser native return validates MCP structure, not PNG bytes; original Browser owner must qualify image integrity before production acceptance")
    async def test_corrupt_png_is_refused_before_native_image_release(self):
        self.native["content"][0]["data"] = base64.b64encode(b"not PNG bytes").decode("ascii")
        result = await self.screenshot()
        self.assertTrue(result["isError"], "Corrupt PNG was forwarded as successful native image content")

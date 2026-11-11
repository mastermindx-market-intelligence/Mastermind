"""Fail-closed unit tests of actual Paper visual evidence capture.

Uses only private temporary files and stdlib mocks. No Paper Desktop or
Peekaboo process starts; Linux GitHub CI must exercise the producer, not only
the SHA comparison consumer. The native macOS path is independently canaried.
"""
import copy
import hashlib
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import zlib

from integrations.paper_desktop import native_page_ui as native


def _png(width=75, height=140):
    """Small structurally valid lossless PNG with nontrivial pixel data."""
    def block(tag, data):
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xffffffff))
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    lines = b"".join(
        b"\x00" + bytes((i + j) % 251 for i in range(width * 3))
        for j in range(height)
    )
    return (b"\x89PNG\r\n\x1a\n" + block(b"IHDR", ihdr)
            + block(b"IDAT", zlib.compress(lines)) + block(b"IEND", b""))


def _context():
    return {
        "logical_bounds": [[508, 55], [2165, 1223]],
        "delivered_image_size": [2165, 1223],
        "output_scale": 1,
        "window": {"window_id": 313},
    }


class NativeVisualFingerprintTests(unittest.TestCase):
    def setUp(self):
        self.private = tempfile.TemporaryDirectory(prefix="paper-visual-test-")
        self.addCleanup(self.private.cleanup)
        self.root = Path(self.private.name)
        self.shot = self.root / "paper-menu.png"
        self.crop = self.root / "sidebar-row.png"
        self.shot.write_bytes(_png(2165, 1223))

    def _capture(self, ctx=None, row_x=100, row_y=165):
        return native._row_visual_fingerprint(
            self.shot, _context() if ctx is None else ctx,
            row_x, row_y, self.crop)

    def test_exact_sips_crop_shape_order_and_digest(self):
        result_bytes = _png()
        self.assertGreater(len(result_bytes), 100)
        expected = [
            "/usr/bin/sips", "-s", "format", "png", "-c", "140", "75",
            "--cropOffset", "105", "15", str(self.shot),
            "--out", str(self.crop),
        ]
        called = []

        def fake_run(args, **kw):
            called.append((args, kw))
            self.assertEqual(args, expected)
            self.assertEqual(kw["timeout"], 6)
            self.assertEqual(kw["check"], False)
            self.assertTrue(kw["capture_output"])
            self.assertFalse(self.crop.exists())
            self.crop.write_bytes(result_bytes)
            return subprocess.CompletedProcess(args, 0)

        with patch.object(native.subprocess, "run", side_effect=fake_run):
            actual = self._capture()
        self.assertEqual(actual, hashlib.sha256(result_bytes).hexdigest())
        self.assertEqual(len(called), 1)

    def test_rejects_stale_crop_even_on_false_success(self):
        self.crop.write_bytes(_png())
        with patch.object(native.subprocess, "run",
                          return_value=subprocess.CompletedProcess([], 0)):
            with self.assertRaisesRegex(native.bridge.Refusal,
                                        "UI_ROW_VISUAL_UNAVAILABLE"):
                self._capture()
        self.assertFalse(self.crop.exists())

    def test_menu_rejects_success_without_fresh_screenshot(self):
        self.shot.write_bytes(_png(2165, 1223))
        self.crop.write_bytes(_png())
        ui = native.NativePeekaboo(binary="fake-peekaboo")
        with patch.object(ui, "_json", return_value={
            "success": True, "data": {"coordinate_context": _context()},
        }) as fake:
            with self.assertRaisesRegex(native.bridge.Refusal,
                                        "UI_ROW_VISUAL_UNVERIFIED"):
                ui.menu(313, self.root, row_x=100, row_y=165)
        fake.assert_called_once()
        self.assertFalse(self.shot.exists())

    def test_menu_rejects_unwritable_stale_shot_before_capture(self):
        ui = native.NativePeekaboo(binary="fake-peekaboo")
        with patch.object(Path, "unlink",
                          side_effect=OSError("synthetic unlink denial")):
            with patch.object(ui, "_json") as sent:
                with self.assertRaisesRegex(native.bridge.Refusal,
                                            "UI_ROW_VISUAL_UNAVAILABLE"):
                    ui.menu(313, self.root, row_x=100, row_y=165)
                sent.assert_not_called()

    def test_menu_fresh_capture_satisfies_real_producer(self):
        new_shot = _png(2165, 1223)
        crop_bytes = _png()
        ui = native.NativePeekaboo(binary="fake-peekaboo")
        def fake_json(args, **kw):
            self.assertFalse(self.shot.exists())
            self.shot.write_bytes(new_shot)
            return {"success": True, "data": {
                "coordinate_context": _context(), "window_title": "Scratch",
            }}
        def fake_sips(args, **kw):
            self.assertEqual(args[0], "/usr/bin/sips")
            self.assertFalse(self.crop.exists())
            self.crop.write_bytes(crop_bytes)
            return subprocess.CompletedProcess(args, 0)

        with patch.object(ui, "_json", side_effect=fake_json):
            with patch.object(native.subprocess, "run", side_effect=fake_sips):
                data = ui.menu(313, self.root, row_x=100, row_y=165)
        self.assertEqual(data["_row_visual_sha256"],
                         hashlib.sha256(crop_bytes).hexdigest())

    def test_context_scale_frame_and_row_guard_before_subprocess(self):
        scenarios = []
        for key, bad in [
            ("output_scale", 2),
            ("output_scale", True),
            ("output_scale", None),
            ("delivered_image_size", [1200, 1223]),
            ("delivered_image_size", [True, 1223]),
            ("delivered_image_size", None),
            ("logical_bounds", [[508, 55], [2165, 0]]),
            ("logical_bounds", None),
        ]:
            ctx = _context()
            ctx[key] = bad
            scenarios.append((key, bad, ctx, 100, 165))
        for x, y in [(84, 165), (191, 165), (100, 1), (True, 165),
                     (100, True), (100, 9000)]:
            scenarios.append(("row", (x, y), _context(), x, y))
        for key, value, ctx, x, y in scenarios:
            with self.subTest(field=key, value=value):
                with patch.object(native.subprocess, "run") as runner:
                    with self.assertRaises(native.bridge.Refusal):
                        self._capture(ctx=ctx, row_x=x, row_y=y)
                    runner.assert_not_called()

    def test_missing_image_fails_before_sips(self):
        self.shot.unlink()
        with patch.object(native.subprocess, "run") as runner:
            with self.assertRaisesRegex(native.bridge.Refusal,
                                        "UI_ROW_VISUAL_UNVERIFIED"):
                self._capture()
            runner.assert_not_called()

    def test_sips_error_timeout_or_nonpng_never_yields_hash(self):
        for label, side_effect, image in (
            ("exit_nonzero", None, _png()),
            ("not_png", None, b"X" * 256),
            ("short_png", None, b"\x89PNG\r\n\x1a\n"),
            ("timeout", subprocess.TimeoutExpired("sips", 6), None),
            ("missing_binary", OSError("sips unavailable"), None),
        ):
            with self.subTest(label=label):
                self.crop.write_bytes(_png())  # stale output must be removed
                def fake_run(args, **kw):
                    if side_effect:
                        raise side_effect
                    if image is not None:
                        self.crop.write_bytes(image)
                    return subprocess.CompletedProcess(
                        args, 1 if label == "exit_nonzero" else 0)
                with patch.object(native.subprocess, "run",
                                  side_effect=fake_run):
                    with self.assertRaisesRegex(native.bridge.Refusal,
                                                "UI_ROW_VISUAL_UNAVAILABLE"):
                        self._capture()


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import os
import time
from types import SimpleNamespace

from integrations.chairman_surfaces import web_sol_native_host as native


INSTANCE_ID = "a" * 64


def test_main_uses_unbuffered_real_pipe_stdio_for_native_framing(monkeypatch):
    """A buffered stdin may prefetch payload beyond the four-byte header.

    The writer deliberately stays open. With a BufferedReader, the first
    ``read(4)`` can pull the complete frame into Python's user-space buffer;
    selecting the underlying descriptor before the payload read then waits for
    bytes that are already buffered and falsely times out. Production main must
    hand the native host the stable unbuffered raw pipe endpoints.
    """

    input_read_fd, input_write_fd = os.pipe()
    output_read_fd, output_write_fd = os.pipe()
    input_buffer = os.fdopen(input_read_fd, "rb")
    output_buffer = os.fdopen(output_write_fd, "wb")
    document = {"probe": "buffered-pipe-regression"}
    os.write(input_write_fd, native.encode_frame(document))

    seen: dict[str, object] = {}

    def fake_run_native_host(chrome_in, chrome_out, **kwargs):
        seen["chrome_in"] = chrome_in
        seen["chrome_out"] = chrome_out
        seen["kwargs"] = kwargs
        seen["document"] = native.read_frame(
            chrome_in,
            deadline=native.Deadline(ends_at=time.monotonic() + 0.25),
        )

    monkeypatch.setattr(native.sys, "stdin", SimpleNamespace(buffer=input_buffer))
    monkeypatch.setattr(native.sys, "stdout", SimpleNamespace(buffer=output_buffer))
    monkeypatch.setattr(native, "run_native_host", fake_run_native_host)

    try:
        assert native.main(
            [
                "web-sol-native-host",
                "--instance-id",
                INSTANCE_ID,
                native.ALLOWED_EXTENSION_ORIGIN,
            ]
        ) == 0
        assert seen["document"] == document
        assert seen["chrome_in"] is input_buffer.raw
        assert seen["chrome_out"] is output_buffer.raw
        assert seen["kwargs"] == {
            "caller_origin": native.ALLOWED_EXTENSION_ORIGIN,
            "expected_instance_id": INSTANCE_ID,
        }
    finally:
        input_buffer.close()
        output_buffer.close()
        os.close(input_write_fd)
        os.close(output_read_fd)

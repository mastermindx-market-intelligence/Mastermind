#!/usr/bin/env python3
"""Closed deterministic PNG source-fingerprint canary over one regular fd."""

import hashlib
import os
import stat
import struct
import sys
import zlib


MAX_BYTES = 65536
WIDTH = 320
HEIGHT = 96
LOWER_HEX = "0123456789abcdef"
DECIMAL = "0123456789"
LABEL_CHARS = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-"
REFUSAL = b"fingerprint-png-refused\n"
SUCCESS = b"fingerprint-png-ok\n"
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def _write_all(fd, payload):
    while payload:
        written = os.write(fd, payload)
        if written <= 0:
            raise OSError("short write")
        payload = payload[written:]


def _refuse():
    try:
        _write_all(sys.stderr.fileno(), REFUSAL)
    except OSError:
        pass
    raise SystemExit(125)


def _valid_fd(raw):
    return bool(raw) and all(character in DECIMAL for character in raw)


def _valid_hash(raw):
    return len(raw) == 64 and all(character in LOWER_HEX for character in raw)


def _valid_label(raw):
    return (
        1 <= len(raw) <= 128
        and raw not in (".", "..")
        and all(character in LABEL_CHARS for character in raw)
    )


def _snapshot(file_stat):
    return (
        file_stat.st_dev,
        file_stat.st_ino,
        file_stat.st_uid,
        file_stat.st_mode,
        file_stat.st_nlink,
        file_stat.st_size,
        file_stat.st_mtime_ns,
        file_stat.st_ctime_ns,
    )


def _safe_regular(file_stat):
    return (
        stat.S_ISREG(file_stat.st_mode)
        and file_stat.st_uid == os.geteuid()
        and file_stat.st_nlink == 1
        and 0 <= file_stat.st_size <= MAX_BYTES
    )


def _safe_root(root_stat, expected_device, expected_inode):
    return (
        stat.S_ISDIR(root_stat.st_mode)
        and root_stat.st_uid == os.geteuid()
        and stat.S_IMODE(root_stat.st_mode) & 0o022 == 0
        and root_stat.st_dev == expected_device
        and root_stat.st_ino == expected_inode
    )


def _read_bounded(fd):
    chunks = []
    total = 0
    while total <= MAX_BYTES:
        chunk = os.read(fd, MAX_BYTES + 1 - total)
        if not chunk:
            break
        chunks.append(chunk)
        total += len(chunk)
        if total > MAX_BYTES:
            _refuse()
    return b"".join(chunks)


def _chunk(kind, payload):
    return (
        struct.pack(">I", len(payload))
        + kind
        + payload
        + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)
    )


def _pixel(digest_bytes, x, y):
    column = min(31, (x * 32) // WIDTH)
    row_band = min(7, (y * 8) // HEIGHT)
    value = digest_bytes[(column + row_band * 5) % 32]
    companion = digest_bytes[(31 - column + row_band * 3) % 32]
    stripe = 30 if ((x // 10) + (y // 12)) % 2 else 0
    red = 24 + ((value * 5 + stripe) % 176)
    green = 32 + ((companion * 3 + stripe) % 160)
    blue = 48 + (((value ^ companion) * 4 + stripe) % 176)
    if x in (0, WIDTH - 1) or y in (0, HEIGHT - 1):
        return 225, 232, 240
    if 8 <= y < 16 and x % 10 < 7:
        bit = (digest_bytes[column] >> (7 - (x % 8))) & 1
        return (235, 245, 255) if bit else (42, 55, 75)
    return red, green, blue


def _render_png(digest, label):
    digest_bytes = bytes.fromhex(digest)
    scanlines = []
    for y in range(HEIGHT):
        row = bytearray((0,))
        for x in range(WIDTH):
            row.extend(_pixel(digest_bytes, x, y))
        scanlines.append(bytes(row))
    metadata = (
        "recipe=source_fingerprint_png;path="
        + label
        + ";sha256="
        + digest
        + ";result=MATCH"
    ).encode("ascii")
    ihdr = struct.pack(">IIBBBBB", WIDTH, HEIGHT, 8, 2, 0, 0, 0)
    return b"".join(
        (
            PNG_SIGNATURE,
            _chunk(b"IHDR", ihdr),
            _chunk(b"tEXt", b"MastermindArtifact\x00" + metadata),
            _chunk(b"IDAT", zlib.compress(b"".join(scanlines), 9)),
            _chunk(b"IEND", b""),
        )
    )


def _run(fd, root_fd, root_device, root_inode, expected_sha256, label):
    if os.read(sys.stdin.fileno(), 1) != b"\x01":
        _refuse()

    root_stat = os.fstat(root_fd)
    if not _safe_root(root_stat, root_device, root_inode):
        _refuse()
    os.fchdir(root_fd)
    if not _safe_root(os.stat("."), root_device, root_inode):
        _refuse()

    initial_stat = os.fstat(fd)
    if not _safe_regular(initial_stat):
        _refuse()
    initial_snapshot = _snapshot(initial_stat)

    os.lseek(fd, 0, os.SEEK_SET)
    data = _read_bounded(fd)

    final_stat = os.fstat(fd)
    if _snapshot(final_stat) != initial_snapshot or len(data) != initial_stat.st_size:
        _refuse()

    digest = hashlib.sha256(data).hexdigest()
    if digest != expected_sha256:
        _refuse()

    output = _render_png(digest, label)
    if not 0 < len(output) <= MAX_BYTES:
        _refuse()
    _write_all(sys.stderr.fileno(), SUCCESS)
    _write_all(sys.stdout.fileno(), output)
    return 0


def main():
    try:
        if len(sys.argv) != 7:
            _refuse()
        raw_fd, raw_root_fd, raw_root_device, raw_root_inode, expected_sha256, label = sys.argv[1:]
        if not all(
            _valid_fd(value)
            for value in (raw_fd, raw_root_fd, raw_root_device, raw_root_inode)
        ):
            _refuse()
        fd = int(raw_fd)
        root_fd = int(raw_root_fd)
        root_device = int(raw_root_device)
        root_inode = int(raw_root_inode)
        if (
            fd < 3
            or root_fd < 3
            or root_device < 0
            or root_inode < 0
            or not _valid_hash(expected_sha256)
            or not _valid_label(label)
        ):
            _refuse()
        return _run(fd, root_fd, root_device, root_inode, expected_sha256, label)
    except (OSError, OverflowError, ValueError, UnicodeError, zlib.error):
        _refuse()


if __name__ == "__main__":
    raise SystemExit(main())

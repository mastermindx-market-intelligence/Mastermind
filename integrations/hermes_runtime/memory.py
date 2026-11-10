"""Append-only RSS high-water log. Lower samples are not recorded."""
from __future__ import annotations

from datetime import datetime, timezone
import os
from pathlib import Path
import re
import stat

from .errors import RuntimeRefusal

_LINE = re.compile(
    r"^(?P<stamp>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z) "
    r"pid=(?P<pid>\d+) rss_kib=(?P<rss>\d+) high_water_kib=(?P<high>\d+)$"
)
_VMRSS = re.compile(r"^VmRSS:\s+(\d+)\s+kB$")


def read_rss_kib(pid: int) -> int | None:
    path = Path(f"/proc/{pid}/status")
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    return parse_vm_rss_kib(text)


def parse_vm_rss_kib(status_text: str) -> int | None:
    for line in status_text.splitlines():
        match = _VMRSS.match(line.strip())
        if match:
            return int(match.group(1))
    return None


class HighWaterLog:
    def __init__(self, path: Path):
        self.path = Path(path)
        if self.path.is_symlink():
            raise RuntimeRefusal("MEMORY_LOG_SYMLINK_REFUSED")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.close(fd)
        self._assert_private()
        self.high_water = self._load()

    def record(self, pid: int, rss_kib: int) -> bool:
        if isinstance(pid, bool) or isinstance(rss_kib, bool):
            raise RuntimeRefusal("MEMORY_SAMPLE_INVALID")
        if not isinstance(pid, int) or not isinstance(rss_kib, int) or pid < 0 or rss_kib < 0:
            raise RuntimeRefusal("MEMORY_SAMPLE_INVALID")
        if rss_kib <= self.high_water:
            return False
        self._assert_private()
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        line = f"{stamp} pid={pid} rss_kib={rss_kib} high_water_kib={rss_kib}\n"
        flags = os.O_APPEND | os.O_WRONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        fd = os.open(self.path, flags)
        try:
            os.write(fd, line.encode("ascii"))
            os.fsync(fd)
        finally:
            os.close(fd)
        self.high_water = rss_kib
        return True

    def _assert_private(self) -> None:
        if self.path.is_symlink():
            raise RuntimeRefusal("MEMORY_LOG_SYMLINK_REFUSED")
        mode = stat.S_IMODE(self.path.stat().st_mode)
        if mode != 0o600:
            raise RuntimeRefusal("MEMORY_LOG_MODE_NOT_0600")

    def _load(self) -> int:
        text = self.path.read_text(encoding="utf-8")
        high = 0
        for raw in text.splitlines():
            if not raw:
                continue
            match = _LINE.fullmatch(raw)
            if not match:
                raise RuntimeRefusal("MEMORY_LOG_CORRUPT")
            rss = int(match.group("rss"))
            recorded = int(match.group("high"))
            if recorded != rss or recorded < high:
                raise RuntimeRefusal("MEMORY_LOG_CORRUPT")
            high = recorded
        return high

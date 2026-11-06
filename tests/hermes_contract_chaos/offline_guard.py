"""Collection/execution regression guard; not an OS sandbox for hostile Python."""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import socket
import subprocess
import urllib.request
from unittest.mock import patch


class OfflineViolation(RuntimeError):
    pass


def forbidden(*args, **kwargs):
    raise OfflineViolation("H24 offline network/process boundary refused")


class OfflineGuard:
    def __init__(self):
        self.root = None
        self.git = shutil.which("git")
        self._popen = subprocess.Popen
        self._connect = socket.socket.connect
        self._patches = []

    def install(self):
        for owner, name, value in (
            (socket.socket, "connect", lambda sock, address: self.connect(sock, address)),
            (socket.socket, "connect_ex", forbidden),
            (socket, "getaddrinfo", forbidden),
            (socket, "create_connection", forbidden),
            (urllib.request, "urlopen", forbidden),
            (subprocess, "Popen", self.popen),
        ):
            item = patch.object(owner, name, value)
            item.start()
            self._patches.append(item)

    def close(self):
        for item in reversed(self._patches):
            item.stop()
        self._patches.clear()
        self.root = None

    def connect(self, sock, address):
        if sock.family in {socket.AF_INET, socket.AF_INET6} or self.root is None:
            return forbidden()
        return self._connect(sock, address)

    def _inside(self, value, cwd):
        path = Path(value)
        path = (path if path.is_absolute() else cwd / path).resolve()
        if not path.is_relative_to(self.root.resolve()):
            return forbidden()
        return path

    def popen(self, args, *positional, **kwargs):
        if (self.root is None or not self.git or not isinstance(args, (list, tuple))
                or len(args) < 2 or kwargs.get("shell") or kwargs.get("executable")):
            return forbidden()
        argv = [os.fspath(value) for value in args]
        if argv[0] not in {"git", self.git}:
            return forbidden()
        cwd = Path(kwargs.get("cwd") or os.getcwd()).resolve()
        offset = 1
        if argv[offset] == "-C":
            if len(argv) < 4:
                return forbidden()
            cwd = self._inside(argv[offset + 1], cwd)
            offset += 2
        verb, operands = argv[offset], argv[offset + 1:]
        allowed = {"init", "config", "add", "commit", "rev-parse", "status", "show", "ls-files",
                   "diff", "log", "ls-tree", "cat-file", "rev-list", "check-ref-format",
                   "clone", "pack-objects", "unpack-objects", "index-pack", "for-each-ref",
                   "update-ref", "checkout", "switch", "symbolic-ref", "merge-base", "remote"}
        if verb not in allowed:
            return forbidden()
        if verb in {"init", "clone"}:
            if not operands or operands[-1].startswith("-"):
                return forbidden()
            self._inside(operands[-1], cwd)
            if verb == "clone":
                if len(operands) < 2 or ":" in operands[-2] or operands[-2].startswith("-"):
                    return forbidden()
                source = self._inside(operands[-2], cwd)
                if not source.is_dir() or any(value not in {
                    "--bare", "--quiet", "-q", "--local", "--no-local", "--no-hardlinks", "--no-checkout",
                } for value in operands[:-2]):
                    return forbidden()
            elif any(value.startswith("--template") or value in {"-c", "--config"}
                     for value in operands[:-1]):
                return forbidden()
            operands = ["--template=", *operands]
        else:
            self._inside(cwd, cwd)
        if verb == "config":
            values = operands[1:] if operands[:1] == ["--local"] else operands
            read = values[:1] == ["--get"] and len(values) == 2 and not values[1].startswith("-")
            write = len(values) == 2 and values[0] in {"user.name", "user.email"}
            if not (read or write):
                return forbidden()
        if verb == "remote" and operands and operands[0] not in {"add", "remove", "set-url", "get-url", "-v"}:
            return forbidden()
        if verb in {"diff", "show", "log"}:
            if "--ext-diff" in operands or "--textconv" in operands:
                return forbidden()
            operands = ["--no-ext-diff", "--no-textconv", *operands]
        env = {key: value for key, value in dict(kwargs.get("env") or os.environ).items()
               if not key.startswith("GIT_")}
        env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_SYSTEM=os.devnull,
                   GIT_CONFIG_GLOBAL=os.devnull, GIT_ATTR_NOSYSTEM="1", GIT_TERMINAL_PROMPT="0",
                   GIT_OPTIONAL_LOCKS="0", GIT_NO_REPLACE_OBJECTS="1")
        kwargs["env"] = env
        safe = [self.git, "--no-pager"]
        for value in ("core.hooksPath=" + os.devnull, "core.fsmonitor=false",
                      "commit.gpgsign=false", "tag.gpgsign=false", "credential.helper=",
                      "protocol.allow=never", "protocol.file.allow=always"):
            safe.extend(("-c", value))
        safe.extend(argv[1:offset])
        return self._popen([*safe, verb, *operands], *positional, **kwargs)

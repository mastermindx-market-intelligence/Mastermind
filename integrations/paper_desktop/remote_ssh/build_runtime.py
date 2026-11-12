#!/usr/bin/env python3
"""Build a NEW, self-contained Paper MCP runtime for SSH forced-command access.

Route B: a remote session reaches the Paper host through `ssh` with a per-host key
whose authorized_keys line forces one fixed gate script. That script ignores the
requested command and starts the guarded stdio MCP server (`mcp_server.py`, which
calls `bridge.py` for every Paper effect). No port is opened and nothing listens.

This builder only creates a folder that does not yet exist. It never replaces,
upgrades or edits another runtime, provider home, sshd setting or key file.

  python3 build_runtime.py --repo <checkout> --commit <40-hex> --dest <new dir> \
      --python <CPython 3.14> [--wheelhouse <dir with the locked wheels>]

Layout of <dest> (all 0700 directories, files 0600 or 0700):
  source/{bridge.py,prepare.py,mcp_server.py}  extracted from the exact commit
  requirements-mcp.lock                         from the same commit
  venv/                                         pip --require-hashes --no-deps
  bin/paper-mcp-read                            gate: read tools only
  bin/paper-mcp-design                          gate: read + prepare + guarded edit
  MANIFEST.json                                 commit, python, sha256 of every file
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

SOURCE = ("bridge.py", "prepare.py", "mcp_server.py")
LOCK = "requirements-mcp.lock"
PREFIX = "integrations/paper_desktop/"
SAFE_PATH = re.compile(r"^/[A-Za-z0-9._/-]+$")
COMMIT = re.compile(r"^[0-9a-f]{40}$")

# Each profile maps to fixed server flags. Nothing from the SSH client chooses them:
# the authorized_keys line names the gate file, and the gate ignores
# SSH_ORIGINAL_COMMAND entirely.
PROFILES = {
    "read": (),
    "design": ("--allow-prepare", "--allow-write"),
}

GATE = """#!/bin/sh
# Mastermind Paper route B gate, profile: {profile}
# Fixed forced command. The client's requested command (SSH_ORIGINAL_COMMAND) is
# ignored. The environment is replaced. stdin/stdout carry MCP JSON-RPC only.
umask 077
exec /usr/bin/env -i HOME={home} PATH=/usr/bin:/bin LANG=en_US.UTF-8 \\
  {python} -I {server}{flags}
"""


def render_gate(profile: str, home: str, python: str, server: str) -> str:
    if profile not in PROFILES:
        raise ValueError(f"unknown profile {profile!r}")
    for value in (home, python, server):
        if not SAFE_PATH.match(value) or "/../" in value or value.endswith("/.."):
            raise ValueError(f"unsafe path for a gate script: {value!r}")
    flags = "".join(f" {f}" for f in PROFILES[profile])
    return GATE.format(profile=profile, home=home, python=python, server=server, flags=flags)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git_show(repo: Path, commit: str, rel: str) -> bytes:
    return subprocess.run(["git", "-C", str(repo), "show", f"{commit}:{rel}"],
                          check=True, capture_output=True).stdout


def write(path: Path, data: bytes, mode: int) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    with os.fdopen(fd, "wb") as fh:
        fh.write(data)
    os.chmod(path, mode)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", required=True)
    ap.add_argument("--commit", required=True)
    ap.add_argument("--dest", required=True)
    ap.add_argument("--python", required=True)
    ap.add_argument("--wheelhouse")
    a = ap.parse_args(argv)
    if not COMMIT.match(a.commit):
        ap.error("--commit must be a full 40-hex commit id")
    dest = Path(a.dest)
    if not dest.is_absolute() or not SAFE_PATH.match(str(dest)):
        ap.error("--dest must be an absolute path with safe characters")
    if dest.exists() or dest.is_symlink():
        ap.error("--dest already exists; this builder never replaces a runtime")
    home = str(Path.home())
    repo = Path(a.repo)

    dest.mkdir(mode=0o700, parents=False)
    for sub in ("source", "bin"):
        (dest / sub).mkdir(mode=0o700)
    for name in SOURCE:
        write(dest / "source" / name, git_show(repo, a.commit, PREFIX + name), 0o600)
    write(dest / LOCK, git_show(repo, a.commit, PREFIX + "remote_ssh/" + LOCK), 0o600)

    subprocess.run([a.python, "-m", "venv", str(dest / "venv")], check=True)
    os.chmod(dest / "venv", 0o700)
    pip = [str(dest / "venv/bin/python"), "-m", "pip", "install", "--require-hashes",
           "--no-deps", "--only-binary=:all:", "--disable-pip-version-check", "-r", str(dest / LOCK)]
    if a.wheelhouse:
        pip += ["--no-index", "--find-links", a.wheelhouse]
    subprocess.run(pip, check=True)

    python = str(dest / "venv/bin/python")
    server = str(dest / "source/mcp_server.py")
    probe = subprocess.run([python, "-I", "-c", "import mcp.server.fastmcp, sys; sys.path.insert(0, sys.argv[1]); import bridge, prepare",
                            str(dest / "source")], capture_output=True, text=True)
    if probe.returncode != 0:
        print(json.dumps({"state": "RUNTIME_IMPORT_FAILED", "stderr": probe.stderr[-400:]}))
        return 3
    for profile in PROFILES:
        write(dest / "bin" / f"paper-mcp-{profile}",
              render_gate(profile, home, python, server).encode(), 0o700)

    manifest = {
        "schema": "mastermind.paper_remote_ssh_runtime.v1",
        "commit": a.commit,
        "python": subprocess.run([python, "-c", "import sys; print(sys.version.split()[0])"],
                                 capture_output=True, text=True).stdout.strip(),
        "files": {str(p.relative_to(dest)): sha256(p)
                  for p in sorted((dest / "source").iterdir()) + sorted((dest / "bin").iterdir())
                  + [dest / LOCK]},
    }
    write(dest / "MANIFEST.json", json.dumps(manifest, indent=1).encode(), 0o600)
    print(json.dumps({"state": "BUILT", "dest": str(dest), **manifest}))
    return 0


if __name__ == "__main__":
    sys.exit(main())

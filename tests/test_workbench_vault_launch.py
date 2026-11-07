"""Real descriptor bootstrap with disposable executable fixtures, no browser.

The original B1 loader's full-closure tests remain in test_worker_browser_b1.
These cases qualify the added fixed entry's custody across the final exec gap.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys

import pytest

from control_plane import worker_browser_b1 as browser

ROOT = Path(__file__).resolve().parents[1]
ENTRY = "node_modules/@mastermind/workbench-vault/child.cjs"


def test_reviewed_receiver_and_lock_pins_match_source_postimages():
    for relative, source in ((ENTRY, "integrations/worker_browser_runtime/vault/child.cjs"),
                             ("package-lock.json", "integrations/worker_browser_runtime/package-lock.json")):
        assert hashlib.sha256((ROOT / source).read_bytes()).hexdigest() == browser._WORKBENCH_CREDENTIAL_SOURCE_PINS[relative]
    raw = (ROOT / "tests/fixtures/hermes_vault/vault_store_upstream.py").read_bytes()
    assert hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest() == "746fbf8a771a7834e1b06a01df96a74df75477ce"
    assert b"MIT License" in (ROOT / "tests/fixtures/hermes_vault/UPSTREAM_LICENSE").read_bytes()


@pytest.mark.parametrize("fault", ["none", "whole-container-replaced", "entry-tampered"])
def test_credential_exec_uses_held_container_and_fixed_reviewed_entry(tmp_path, fault):
    container = tmp_path / "worker-browser-b1"
    runtime = container / "runtime"
    node = runtime / "bin/node"
    cli = runtime / "node_modules/@playwright/mcp/cli.js"
    entry = runtime / ENTRY
    for path in (node, cli, entry): path.parent.mkdir(parents=True, exist_ok=True)
    node.write_text('#!/bin/sh\nprintf "ORIGINAL:%s:%s\\n" "$1" "$2"\n')
    node.chmod(0o500)
    cli.write_text("synthetic CLI identity fixture")
    cli.chmod(0o500)
    entry.write_bytes((ROOT / "integrations/worker_browser_runtime/vault/child.cjs").read_bytes())
    entry.chmod(0o400)
    def identity(path):
        s = path.stat()
        return {"gid": s.st_gid, "uid": s.st_uid, "mode": stat.S_IMODE(s.st_mode),
                "path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    entry_identity = identity(entry)
    ci = container.stat()
    manifest = {"runtime_root": str(runtime),
        "runtime_container": {"device": ci.st_dev, "inode": ci.st_ino, "uid": ci.st_uid, "gid": ci.st_gid, "mode": 0o500},
        "node": {"executable": identity(node)}, "mcp": {"executable": identity(cli)},
        "closure_inventory": [{**entry_identity, "path": ENTRY, "type": "file", "link": ""}]}
    manifest_path = runtime / browser.RUNTIME_INSTALL_MANIFEST_NAME
    manifest_path.write_bytes(browser._canonical_bytes(manifest) + b"\n")
    manifest_path.chmod(0o400)
    digest = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    for path in sorted((p for p in container.rglob("*") if p.is_dir()), key=lambda p: len(p.parts), reverse=True):
        path.chmod(0o500)
    container.chmod(0o500)
    fd = os.open(container, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        if fault == "whole-container-replaced":
            container.rename(tmp_path / "held-original")
            replacement = container / "runtime/bin/node"
            replacement.parent.mkdir(parents=True)
            replacement.write_text('#!/bin/sh\nprintf "REPLACEMENT\\n"\n')
            replacement.chmod(0o500)
        elif fault == "entry-tampered":
            entry.chmod(0o600)
            entry.write_text("changed receiver")
            entry.chmod(0o400)
        completed = subprocess.run([sys.executable, "-I", "-S", "-c", browser._credential_node_bootstrap(),
            "runtime/browsers/fixture", str(tmp_path), "c" * 32, "9999999999999"],
            env={"HOME": str(tmp_path), "TMPDIR": str(tmp_path), "LANG": "C", "LC_ALL": "C", "NO_COLOR": "1", "PATH": "/usr/bin:/bin",
                 "MASTERMIND_BROWSER_RUNTIME_CONTAINER_FD": str(fd),
                 "MASTERMIND_BROWSER_RUNTIME_MANIFEST_SHA256": digest, "PLAYWRIGHT_BROWSERS_PATH": "runtime/browsers"},
            pass_fds=(fd,), text=True, capture_output=True, timeout=10)
    finally:
        os.close(fd)
        # Permit pytest's normal disposable-directory cleanup.
        for path in tmp_path.rglob("*"):
            if path.is_dir(): path.chmod(0o700)
    if fault == "entry-tampered":
        assert completed.returncode != 0
        assert "ORIGINAL" not in completed.stdout
    else:
        assert completed.returncode == 0, completed.stderr
        assert completed.stdout == "ORIGINAL:runtime/" + ENTRY + ":runtime\n"
        assert "REPLACEMENT" not in completed.stdout

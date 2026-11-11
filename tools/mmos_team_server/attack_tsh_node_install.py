#!/usr/bin/env python3
"""Five reproducible, local-only attacks against the Node installer.

Run with the REAL official archive and official checksum record as arguments;
the official digest is not replaced by a fixture-specific value. No downloaded
executable is run and no server or LaunchAgent is touched. Files are created
under a newly created, private temporary directory. A foreign-owner condition
is simulated at stat, since this unprivileged reproducer cannot chown.
"""
import importlib.util
import os
import sys
import tempfile
from pathlib import Path

TOOL = Path(__file__).resolve().parent / "node_install.py"
loader = importlib.util.spec_from_file_location("tsh_node_install", TOOL)
module = importlib.util.module_from_spec(loader)
loader.loader.exec_module(module)


def run_attacks(archive, checksum):
    archive = os.path.abspath(archive)
    checksum = os.path.abspath(checksum)
    if module.sha256(archive) != module.OFFICIAL_SHA256:
        raise module.InstallError("reproducer requires the official pinned archive")
    failures = []
    with tempfile.TemporaryDirectory(prefix="tsh-node-attacks-") as temp:
        for scenario in ("tampered-archive", "invalid-checksum", "symlink-directory",
                         "foreign-owner", "half-finished"):
            root = Path(temp) / scenario
            root.mkdir(mode=0o700)
            held = False
            try:
                if scenario == "tampered-archive":
                    candidate = Path(temp) / "tampered" / module.ARCHIVE
                    candidate.parent.mkdir()
                    source = Path(archive).read_bytes()
                    # Preserve the required filename while changing one byte;
                    # the official checksum must refuse before extraction.
                    candidate.write_bytes(source[:-1] + bytes([source[-1] ^ 1]))
                    module.install_node(str(root), str(candidate), checksum)
                elif scenario == "invalid-checksum":
                    bad = Path(temp) / "invalid.checked"
                    bad.write_text("not a SHA-256 record\n")
                    module.install_node(str(root), archive, str(bad))
                elif scenario == "symlink-directory":
                    destination = Path(temp) / "symlink-target"
                    destination.mkdir()
                    (root / "runtime").symlink_to(destination, target_is_directory=True)
                    module.install_node(str(root), archive, checksum)
                elif scenario == "foreign-owner":
                    real_stat = module.os.stat
                    def foreign(path, **kwargs):
                        result = real_stat(path, **kwargs)
                        if os.path.abspath(path) == archive:
                            values = tuple(result)
                            return result.__class__(values[:4] + (0,) + values[5:])
                        return result
                    original = module.os.lstat
                    module.os.lstat = foreign
                    try:
                        module.install_node(str(root), archive, checksum)
                    finally:
                        module.os.lstat = original
                else:
                    (root / "runtime/staging/interrupted").mkdir(parents=True, mode=0o700)
                    module.install_node(str(root), archive, checksum)
            except module.InstallError as exc:
                held = "nodePath" not in str(exc) and not (
                    root / "config/node-runtime.json").exists()
                detail = str(exc)[:150]
            if held:
                print(f"ATTACK {scenario}: HELD — {detail}")
            else:
                failures.append(scenario)
                print(f"ATTACK {scenario}: BYPASS — destination was activated or unchecked")
    print(f"ATTACK SUMMARY: {5 - len(failures)} HELD, {len(failures)} BYPASS")
    return 1 if failures else 0


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("usage: attack_tsh_node_install.py OFFICIAL_ARCHIVE OFFICIAL_SHA256SUMS",
              file=sys.stderr)
        sys.exit(2)
    try:
        sys.exit(run_attacks(sys.argv[1], sys.argv[2]))
    except (module.InstallError, OSError, ValueError) as exc:
        print(f"REPRODUCER_FAILED: {str(exc)[:180]}", file=sys.stderr)
        sys.exit(1)

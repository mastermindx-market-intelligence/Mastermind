#!/usr/bin/env python3
"""Verify source data and rehearse frozen tests in a fresh disposable HOME; never install."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile

PACKAGE = Path(__file__).resolve().parent
MACRO_PIN = "b03edd4902a5582ed59773ec12ff2c2fa37aadf7"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify():
    manifest = json.loads((PACKAGE / "manifest.json").read_text())
    for row in manifest["files"]:
        path = PACKAGE / row["path"]
        if path.is_symlink() or path.resolve().parent != path.parent.resolve():
            raise ValueError("Package member must be a regular nonsymlink file")
        if not path.is_file() or PACKAGE not in path.resolve().parents:
            raise ValueError("Package member outside the source package")
        if digest(path) != row["sha256"] or path.stat().st_size != row["bytes"]:
            raise ValueError("Frozen package bytes differ: " + row["path"])
        if path.stat().st_mode & 0o777 != int(row["mode"], 8):
            raise ValueError("Frozen package mode differs: " + row["path"])
    return manifest


def reconstruct(root):
    for relative, source in (("gwcap/bin/mmtask", "preimage/mmtask"),
                             ("gwcap/bin/mmtask-repair/test_mmtask.py", "preimage/test_mmtask.py.source")):
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(PACKAGE / source, target)
    patch = PACKAGE / "mmtask-selector-recovery.patch"
    headers = [line.split("\t", 1)[0][4:] for line in patch.read_text().splitlines()
               if line.startswith(("--- ", "+++ "))]
    expected = {"a/gwcap/bin/mmtask", "b/gwcap/bin/mmtask",
                "a/gwcap/bin/mmtask-repair/test_mmtask.py", "b/gwcap/bin/mmtask-repair/test_mmtask.py"}
    if set(headers) != expected:
        raise ValueError("Patch target scope differs")
    result = subprocess.run(["patch", "--batch", "--fuzz=0", "--forward", "-p1", "-i", str(patch)],
                            cwd=root, capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError("Frozen patch did not reconstruct: " + result.stdout + result.stderr)
    for target, payload in ((root / "gwcap/bin/mmtask", PACKAGE / "payload/mmtask"),
                            (root / "gwcap/bin/mmtask-repair/test_mmtask.py", PACKAGE / "payload/test_mmtask.py.source")):
        if target.read_bytes() != payload.read_bytes():
            raise ValueError("Patch postimage differs from frozen payload")
    return result.stdout


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-only", action="store_true")
    parser.add_argument("--macro-repo", type=Path)
    parser.add_argument("--result", type=Path, help="Create a new result file; existing files are preserved")
    args = parser.parse_args()
    manifest = verify()
    if args.verify_only:
        print(json.dumps({"status": "FROZEN_SOURCE_VERIFIED", "files": len(manifest["files"])}))
        return 0
    if not args.macro_repo or not args.result:
        parser.error("Rehearsal requires --macro-repo and a new --result path")
    # Reserve output before any test execution. No real HOME/charter/helper path is a target.
    result_fd = os.open(args.result, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(result_fd, "w") as receipt:
        report = {"status": "STARTED", "macro_commit": MACRO_PIN, "source_manifest_sha256": digest(PACKAGE / "manifest.json")}
        json.dump(report, receipt); receipt.flush()
        try:
            with tempfile.TemporaryDirectory(prefix="mmtask-source-rehearsal-") as temp:
                root = Path(temp)
                patch_stdout = reconstruct(root / "patch-proof")
                home = root / "home"; home.mkdir()
                tmp = root / "tmp"; tmp.mkdir()
                mirror = home / "gwcap/agentos-mirror/macro"; mirror.mkdir(parents=True)
                archive = subprocess.run(["git", "-C", str(args.macro_repo.resolve()), "archive", MACRO_PIN, "agentos", "scripts"], capture_output=True, check=True).stdout
                with tarfile.open(fileobj=io.BytesIO(archive)) as bundle:
                    bundle.extractall(mirror, filter="data")
                source = root / "frozen-tests"; source.mkdir()
                shutil.copy2(PACKAGE / "payload/test_mmtask.py.source", source / "test_mmtask.py")
                shutil.copytree(PACKAGE / "payload/fixtures", source / "fixtures")
                env = {key: value for key, value in os.environ.items() if key in ("PATH", "SYSTEMROOT", "LANG", "LC_ALL")}
                env.update(HOME=str(home), TMPDIR=str(tmp), MMTASK_UNDER_TEST=str(PACKAGE / "payload/mmtask"),
                           MM_AGENTOS_MIRROR=str(mirror), PYTHONNOUSERSITE="1", PYTHONDONTWRITEBYTECODE="1")
                import yaml
                env["PYTHONPATH"] = str(Path(yaml.__file__).parent.parent)
                test = subprocess.run([sys.executable, str(source / "test_mmtask.py")], cwd=home, env=env,
                                      capture_output=True, text=True)
                report.update(status="PASS" if test.returncode == 0 else "FAIL", exit_code=test.returncode,
                              python=sys.version, pyyaml=yaml.__version__, archive_sha256=hashlib.sha256(archive).hexdigest(),
                              fixture_sha256=digest(PACKAGE / "payload/fixtures/shared-shell-TASKS.null-bound.json"),
                              patch_reconstruction=patch_stdout, stdout=test.stdout, stderr=test.stderr,
                              isolation="fresh HOME/TMPDIR, tracked Macro archive without .git, explicit frozen helper; no live helper/charter execution")
        except Exception as error:
            report.update(status="ERROR", error=str(error))
        receipt.seek(0); receipt.truncate(); json.dump(report, receipt, indent=2); receipt.write("\n")
    print(json.dumps({key: value for key, value in report.items() if key not in ("stdout", "stderr", "patch_reconstruction")}))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())

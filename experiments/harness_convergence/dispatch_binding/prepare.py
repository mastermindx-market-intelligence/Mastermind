"""Prepare only hash-pinned donor test inputs; never install or start DSH."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import tempfile
import urllib.request
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parent
CACHE = ROOT / ".cache"
MANIFEST = json.loads((ROOT / "donor-manifest.json").read_text())


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def check(data: bytes, entry: dict) -> None:
    blob = hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()
    if len(data) != entry["bytes"] or digest(data) != entry["sha256"] or blob != entry["git_blob"]:
        raise ValueError(f"Donor identity mismatch: {entry['path']}")


def retain(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.exists():
        if path.read_bytes() != data:
            raise ValueError(f"Unexpected existing artifact; preserve and reconcile: {path}")
    else:
        with path.open("xb") as stream:
            stream.write(data)


def prepare(download: bool = False) -> dict:
    if MANIFEST["repository"] != "deepseek-ai/deepseek-harness":
        raise ValueError("Unexpected donor repository")
    for entry in MANIFEST["files"]:
        relative = PurePosixPath(entry["path"])
        if relative.is_absolute() or ".." in relative.parts or relative.name != entry["name"]:
            raise ValueError("Invalid donor source path")
        target = CACHE / ("pristine" if entry["kind"] == "source" else "tests") / relative.name
        if target.exists():
            data = target.read_bytes()
        elif download:
            url = f"https://raw.githubusercontent.com/{MANIFEST['repository']}/{MANIFEST['commit']}/{relative}"
            with urllib.request.urlopen(url, timeout=20) as response:
                data = response.read(entry["bytes"] + 1)
        else:
            raise FileNotFoundError(f"Missing {target}; explicit prepare.py --download is required")
        check(data, entry)
        retain(target, data)
    patch = ROOT / MANIFEST["patch_file"]
    if digest(patch.read_bytes()) != MANIFEST["patch_sha256"]:
        raise ValueError("Patch digest mismatch")
    CACHE.mkdir(exist_ok=True, mode=0o700)
    for directory in ["home", "tmp"]:
        (CACHE / directory).mkdir(exist_ok=True, mode=0o700)
    # A temporary artifact transform, not a checkout or another source owner.
    with tempfile.TemporaryDirectory(prefix="apply-", dir=CACHE) as temporary:
        staging = Path(temporary)
        source = staging / "packages/core/tools/src/index.ts"
        source.parent.mkdir(parents=True)
        shutil.copyfile(CACHE / "pristine/index.ts", source)
        result = subprocess.run(
            ["patch", "--batch", "--forward", "-p1", "-i", str(patch)],
            cwd=staging, capture_output=True, text=True, timeout=15, check=False,
            env={"PATH": "/usr/bin:/bin", "HOME": str(CACHE / "home"), "TMPDIR": str(CACHE / "tmp")},
        )
        if result.returncode:
            raise RuntimeError(f"Patch did not apply: {result.stdout}{result.stderr}")
        patched = source.read_bytes()
        if digest(patched) != MANIFEST["patched_index_sha256"]:
            raise ValueError("Patched source digest mismatch")
        retain(CACHE / "donor/index.ts", patched)
    for entry in MANIFEST["files"]:
        if entry["kind"] == "source" and entry["name"] != "index.ts":
            retain(CACHE / "donor" / entry["name"], (CACHE / "pristine" / entry["name"]).read_bytes())
    for directory in ["home", "tmp", "npm-cache"]:
        (CACHE / directory).mkdir(exist_ok=True, mode=0o700)
    for name in ["empty-user.npmrc", "empty-global.npmrc"]:
        retain(CACHE / name, b"")
    return {"source_files": len(MANIFEST["files"]), "commit": MANIFEST["commit"],
            "patched_sha256": digest(patched), "runtime_started": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--download", action="store_true", help="Fetch missing public sources once; no retries")
    args = parser.parse_args()
    print(json.dumps(prepare(args.download), indent=2))

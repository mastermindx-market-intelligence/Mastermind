"""Hash-pinned MCP bridge source preparation; no server or provider is started."""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import tempfile
import urllib.request
from pathlib import Path, PurePosixPath
from prepare import ROOT, CACHE, check, digest, retain

MANIFEST = json.loads((ROOT / "mcp-manifest.json").read_text())


def prepare(download: bool = False) -> dict:
    if MANIFEST["repository"] != "deepseek-ai/deepseek-harness":
        raise ValueError("Unexpected donor repository")
    for entry in MANIFEST["files"]:
        relative = PurePosixPath(entry["path"])
        folder = entry["folder"]
        if (relative.is_absolute() or ".." in relative.parts
                or relative.name != entry["name"]
                or folder not in {"mcp-pristine", "mcp-tests"}):
            raise ValueError("Unexpected source path")
        target = CACHE / folder / relative.name
        if target.is_symlink() or target.parent.is_symlink():
            raise ValueError("Source cache must not be a symlink")
        if target.exists():
            data = target.read_bytes()
        elif download:
            url = f"https://raw.githubusercontent.com/{MANIFEST['repository']}/{MANIFEST['commit']}/{relative}"
            with urllib.request.urlopen(url, timeout=20) as response:
                data = response.read(entry["bytes"] + 1)
        else:
            raise FileNotFoundError(f"Missing {target}; use explicit --download")
        check(data, entry)
        retain(target, data)
    patch = ROOT / MANIFEST["patch_file"]
    if digest(patch.read_bytes()) != MANIFEST["patch_sha256"]:
        raise ValueError("MCP patch digest mismatch")
    for name in ["home", "tmp"]:
        (CACHE / name).mkdir(parents=True, exist_ok=True, mode=0o700)
    with tempfile.TemporaryDirectory(prefix="mcp-apply-", dir=CACHE) as temporary:
        staging = Path(temporary)
        source = staging / "packages/mcp/mcp-client/src"
        source.mkdir(parents=True)
        for entry in MANIFEST["files"]:
            if entry["folder"] == "mcp-pristine":
                shutil.copyfile(CACHE / "mcp-pristine" / entry["name"], source / entry["name"])
        result = subprocess.run(
            ["patch", "--batch", "--forward", "-F0", "-p1", "-i", str(patch)],
            cwd=staging, capture_output=True, text=True, timeout=15, check=False,
            env={"PATH": "/usr/bin:/bin", "HOME": str(CACHE / "home"), "TMPDIR": str(CACHE / "tmp")},
        )
        if result.returncode:
            raise RuntimeError(f"MCP patch did not apply: {result.stdout}{result.stderr}")
        for entry in MANIFEST["files"]:
            if entry["folder"] != "mcp-pristine":
                continue
            name = entry["name"]
            expected = MANIFEST["patched_source_sha256"].get(name, entry["sha256"])
            data = (source / name).read_bytes()
            if digest(data) != expected:
                raise ValueError(f"Patched MCP source mismatch: {name}")
            target = CACHE / "mcp-donor" / name
            if target.is_symlink() or target.parent.is_symlink():
                raise ValueError("Patched cache must not be a symlink")
            retain(target, data)
    return {"commit": MANIFEST["commit"], "source_files": len(MANIFEST["files"]),
            "patch_sha256": MANIFEST["patch_sha256"],
            "patched_source_sha256": MANIFEST["patched_source_sha256"],
            "runtime_started": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--download", action="store_true", help="Fetch missing fixed public inputs once")
    args = parser.parse_args()
    print(json.dumps(prepare(args.download), indent=2))

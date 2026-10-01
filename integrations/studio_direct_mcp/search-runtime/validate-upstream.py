#!/usr/bin/env python3
"""Materialize the pinned upstream build input and validate the #1027 patch.
No installed runtime, account configuration, service or Git checkout is modified.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tarfile
import urllib.request

PIN = "56b5127ec6539f1d182ed4c3ffdeb114cf6bfd66"
BLOBS = {
    "src/search-manager.ts": "59b29580591167efcd39c1fc71b8f3f500a6a5e1",
    "src/handlers/search-handlers.ts": "40a1b268d29e4fa392abd2bc9ef758b824982031",
}
TESTS = [
    "test-search-files-literal.js", "test-search-files-file-pattern.js",
    "test-search-file-pattern.js", "test-search-office-any-folder.js",
    "test-search-error-output.js", "test-search-process-exit.js",
    "test-search-stopped-not-failed.js",
]

class LimitedReader:
    def __init__(self, stream):
        self.stream, self.count = stream, 0
    def read(self, size=-1):
        data = self.stream.read(min(size if size >= 0 else 65536, 65536))
        self.count += len(data)
        if self.count > 128 * 1024 * 1024:
            raise RuntimeError("compressed upstream source exceeds 128 MiB")
        return data

def run(argv, root, log):
    with log.open("w") as output:
        subprocess.run(argv, cwd=root, stdout=output, stderr=subprocess.STDOUT,
                       timeout=180, check=True)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path,
                        help="New disposable build/evidence directory")
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    root = output / "upstream"
    root.mkdir()
    selected_bytes = 0
    url = f"https://codeload.github.com/wonderwhy-er/DesktopCommanderMCP/tar.gz/{PIN}"
    with urllib.request.urlopen(url, timeout=30) as response:
        with tarfile.open(fileobj=LimitedReader(response), mode="r|gz") as archive:
            for member in archive:
                parts = Path(member.name).parts[1:]
                if not parts or ".." in parts or not member.isfile():
                    continue
                if parts[0] not in ("src", "test", "scripts") and len(parts) != 1:
                    continue
                if member.size > 8 * 1024 * 1024:
                    continue
                selected_bytes += member.size
                if selected_bytes > 32 * 1024 * 1024:
                    raise RuntimeError("selected source exceeds 32 MiB")
                target = root.joinpath(*parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(archive.extractfile(member).read())
    for name, expected in BLOBS.items():
        data = (root / name).read_bytes()
        actual = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
        if actual != expected:
            raise RuntimeError(f"donor blob mismatch: {name}")
    patch = Path(__file__).resolve().with_name("candidate.patch")
    run(["patch", "-p1", "-i", str(patch)], root, output / "patch.log")
    run(["npm", "ci", "--ignore-scripts", "--no-audit", "--no-fund"],
        root, output / "npm-ci.log")
    run(["npm", "run", "build"], root, output / "build.log")
    # Upstream runner isolates configuration/home and disables telemetry.
    run(["node", "test/run-all-tests.js", *TESTS], root, output / "tests.log")
    report = {"donor": PIN, "patchSHA256": hashlib.sha256(patch.read_bytes()).hexdigest(),
              "packageBuild": "PASS", "upstreamSuites": TESTS,
              "scope": "source qualification only; not installed acceptance"}
    (output / "qualification.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))

if __name__ == "__main__":
    main()

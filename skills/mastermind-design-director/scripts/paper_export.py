#!/usr/bin/env python3
"""Read-only batch export of Paper artboard screenshots through the guarded bridge CLI.

Runs on the Paper host. It calls only `get_basic_info` (with pageId) and
`get_screenshot` (by explicit nodeId), never an edit, page switch or selection read.
Each image is saved under its node id, with its sha256 in an index. It makes no retry:
a failed call is recorded and the next node is tried.

  python3 paper_export.py --bridge <bridge.py> --python <venv python> \
      --file <fileId> --page <pageId> [--page ...] [--node <id> ...] \
      [--skip <id> ...] --out <new private dir> [--scale 1] [--max-calls 200]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
FILE_ID = re.compile(r"^[0-9A-HJKMNP-TV-Z]{26}$")


def call(py: str, bridge: str, tool: str, args: dict, scratch: Path, artifacts: Path | None):
    argfile = scratch / "args.json"
    argfile.write_text(json.dumps(args), encoding="utf-8")
    cmd = [py, bridge, "read", "--tool", tool, "--arguments", f"@{argfile}"]
    if artifacts is not None:
        cmd += ["--artifact-dir", str(artifacts)]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {"state": "NO_JSON", "stderr": proc.stderr[-300:]}


def artboards(reply: dict) -> list[dict]:
    for block in reply.get("result", {}).get("content", []):
        if block.get("type") == "text":
            try:
                data = json.loads(block["text"])
            except (json.JSONDecodeError, KeyError):
                continue
            if "artboards" in data:
                return data["artboards"]
    return []


def safe(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9-]+", "-", name or "").strip("-")[:50] or "artboard"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bridge", required=True)
    ap.add_argument("--python", required=True)
    ap.add_argument("--file", required=True)
    ap.add_argument("--page", action="append", default=[])
    ap.add_argument("--node", action="append", default=[])
    ap.add_argument("--skip", action="append", default=[])
    ap.add_argument("--out", required=True)
    ap.add_argument("--scale", type=float, default=1)
    ap.add_argument("--max-calls", type=int, default=200)
    a = ap.parse_args(argv)
    if not FILE_ID.match(a.file):
        ap.error("--file must be an exact Paper file id")
    for value in a.page + a.node + a.skip:
        if not ID.match(value):
            ap.error(f"invalid id: {value!r}")
    if not (a.page or a.node):
        ap.error("give at least one --page or --node")
    out = Path(a.out)
    if out.exists():
        ap.error("--out must not exist yet (no overwrite)")
    out.mkdir(mode=0o700, parents=True)
    skip = set(a.skip)
    calls = 0
    index = {"file_id": a.file, "items": [], "failures": [], "skipped": sorted(skip)}
    with tempfile.TemporaryDirectory(prefix="paper-export-") as tmp:
        scratch = Path(tmp)
        os.chmod(scratch, 0o700)
        targets: list[tuple[str, str, dict]] = [(n, "", {}) for n in a.node]
        for page in a.page:
            if calls >= a.max_calls:
                break
            calls += 1
            reply = call(a.python, a.bridge, "get_basic_info", {"fileId": a.file, "pageId": page}, scratch, None)
            if reply.get("state") != "OBSERVED":
                index["failures"].append({"page": page, "state": reply.get("state")})
                continue
            targets += [(b["id"], page, b) for b in artboards(reply)]
        for node, page, meta in targets:
            if node in skip:
                continue
            if calls >= a.max_calls:
                index["failures"].append({"node": node, "state": "CALL_BUDGET_EXHAUSTED"})
                continue
            calls += 1
            art = scratch / f"a{calls}"
            art.mkdir(mode=0o700)
            reply = call(a.python, a.bridge, "get_screenshot",
                         {"fileId": a.file, "nodeId": node, "scale": a.scale}, scratch, art)
            paths = reply.get("artifact_paths") or []
            if reply.get("state") != "OBSERVED" or not paths:
                index["failures"].append({"node": node, "state": reply.get("state")})
                continue
            src = Path(paths[0])
            dest_dir = out / (page or "nodes")
            dest_dir.mkdir(mode=0o700, exist_ok=True)
            dest = dest_dir / f"{node}_{safe(meta.get('name', ''))}{src.suffix}"
            shutil.copyfile(src, dest)
            digest = hashlib.sha256(dest.read_bytes()).hexdigest()
            index["items"].append({"node": node, "page": page, "name": meta.get("name"),
                                   "width": meta.get("width"), "height": meta.get("height"),
                                   "path": str(dest.relative_to(out)), "sha256": digest})
    index["paper_calls"] = calls
    (out / "index.json").write_text(json.dumps(index, indent=1), encoding="utf-8")
    print(json.dumps({"exported": len(index["items"]), "failures": len(index["failures"]),
                      "paper_calls": calls, "index": str(out / "index.json")}))
    return 0 if not index["failures"] else 1


if __name__ == "__main__":
    sys.exit(main())

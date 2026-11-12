#!/usr/bin/env python3
"""Package the stdlib-only T3 team compiler; no install, launch or profile edits."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess
import sys
import zipfile

FILES = (
    "common/coo_project_help_contract.py",
    "common/paperclip_contract.py",
    "common/project_task_contract.py",
    "common/workspace_project_plan_contract.py",
    "integrations/session_bridge/project_task_context.py",
    "integrations/session_bridge/t3_mission_brief.py",
    "integrations/session_bridge/t3_web_client.py",
    "integrations/session_bridge/t3_project_team.py",
    "integrations/session_bridge/t3_project_team_inventory.py",
    "integrations/session_bridge/t3_project_team_cli.py",
)


def archive_bytes(source_root: Path, *, source_revision: str | None = None) -> tuple[bytes, dict]:
    contents = {path: (source_root / path).read_bytes() for path in FILES}
    if source_revision is not None:
        if type(source_revision) is not str or re.fullmatch(r"[0-9a-f]{40}", source_revision) is None:
            raise ValueError("Exact source commit required")
        head = subprocess.check_output(
            ["git", "-C", str(source_root), "rev-parse", "HEAD"], timeout=10).decode().strip()
        if head != source_revision:
            raise ValueError("Source HEAD changed")
        for path, captured in contents.items():
            committed = subprocess.check_output(
                ["git", "-C", str(source_root), "show", source_revision + ":" + path], timeout=10)
            if committed != captured:
                raise ValueError("Package source differs from the committed revision")
        # Build exactly the captured and verified bytes, not a second filesystem
        # read that could race with an edit after source qualification.
    manifest = {"schema": "mastermind.t3_project_team_package.v1", "source_revision": source_revision,
                "source_status": "exact_committed_bytes" if source_revision else "qualification_only",
                "files": {path: hashlib.sha256(raw).hexdigest() for path, raw in contents.items()},
                "runtime_effects": "none; caller imports or executes read-only compiler commands"}
    contents.update({
        "common/__init__.py": b"",
        "integrations/__init__.py": b"",
        "integrations/session_bridge/__init__.py": b"",
        "__main__.py": b"from integrations.session_bridge.t3_project_team_cli import main\nraise SystemExit(main())\n",
        "build.json": (json.dumps(manifest, sort_keys=True, indent=2) + "\n").encode(),
    })
    stream = io.BytesIO()
    stream.write(b"#!/usr/bin/env python3\n")
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, raw in sorted(contents.items()):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.external_attr = 0o644 << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, raw)
    return stream.getvalue(), manifest


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--expected-head", required=True)
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    try:
        payload, manifest = archive_bytes(root, source_revision=args.expected_head)
        # Exclusive creation: a package build cannot replace another installed generation.
        with args.output.open("xb") as stream:
            stream.write(payload)
        args.output.chmod(0o755)
        print(json.dumps({"sha256": hashlib.sha256(payload).hexdigest(), "bytes": len(payload),
                          "manifest": manifest, "installed": False}, sort_keys=True))
        return 0
    except (OSError, ValueError, subprocess.SubprocessError):
        print(json.dumps({"error": "PACKAGE_SOURCE_OR_DESTINATION_NOT_QUALIFIED", "installed": False}))
        return 2


if __name__ == "__main__":
    sys.exit(main())

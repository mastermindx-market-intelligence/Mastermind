#!/usr/bin/env python3
"""Build a standalone Hermes plugin from canonical sources; no registration.

Use an empty build destination, never a live profile's plugin directory. The
native plugin installer remains the owner of installation and activation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import tempfile

MAPPING = {
    "__init__.py": "integrations/session_bridge/hermes_project_plugin.py",
    "project_task_context.py": "integrations/session_bridge/project_task_context.py",
    "project_task_contract.py": "common/project_task_contract.py",
    "long_horizon_guidance.py": "integrations/session_bridge/long_horizon_guidance.py",
    "plugin.yaml": "integrations/session_bridge/hermes_project_plugin.yaml",
    "skill/SKILL.md": "skills/mastermind-long-horizon/SKILL.md",
    "skill/references/native-t3.md": "skills/mastermind-long-horizon/references/native-t3.md",
    "skill/references/native-hermes.md": "skills/mastermind-long-horizon/references/native-hermes.md",
    "skill/references/continuity-patterns.md": "skills/mastermind-long-horizon/references/continuity-patterns.md",
}


def build(output: Path, *, source_root: Path | None = None) -> dict:
    root = source_root or Path(__file__).resolve().parents[1]
    if not output.is_absolute() or output.exists() or output.is_symlink():
        raise ValueError("PLUGIN_BUILD_REQUIRES_NEW_ABSOLUTE_DESTINATION")
    # This builder must never become a second native installation path.
    if ".hermes" in output.parts or output.parent.name == "plugins":
        raise ValueError("PLUGIN_BUILD_NOT_A_NATIVE_INSTALLER")
    parent = output.parent.resolve(strict=True)
    payload = {}
    for target, source in MAPPING.items():
        path = root / source
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 128 * 1024:
            raise ValueError("PLUGIN_BUILD_SOURCE_INVALID")
        payload[target] = path.read_bytes()
    receipt = {"schema": "mastermind.hermes_horizon_package.v1", "installed": False,
        "files": {target: {"source": MAPPING[target], "sha256": hashlib.sha256(raw).hexdigest()}
                  for target, raw in payload.items()}}
    with tempfile.TemporaryDirectory(prefix=".mmx-horizon-build-", dir=parent) as temp:
        stage = Path(temp) / "package"
        stage.mkdir()
        for target, raw in payload.items():
            dest = stage / target
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(raw)
        (stage / "SOURCE_MANIFEST.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
        if output.exists() or output.is_symlink():
            raise ValueError("PLUGIN_BUILD_DESTINATION_CHANGED")
        # copytree creates the final directory exclusively; a racing existing
        # destination is never replaced, even when it is empty. No runtime writes.
        shutil.copytree(stage, output)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = build(args.output)
    print(json.dumps({"output": str(args.output), **result}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

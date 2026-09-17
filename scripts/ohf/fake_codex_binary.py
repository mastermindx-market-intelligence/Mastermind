#!/usr/bin/env python3
"""CAP-S1 single-binary fixture: schema generation, --version, and the App
Server itself -- all ONE file (CAP-S1 Sol review item 1, single-binary law).

Before this commission the fake realm launched TWO different files as "the
binary": a print-and-write schema-fixture script for
``generate-json-schema``/``--version``, and the running Python interpreter
(via ``-m scripts.ohf.fake_app_server``) for the actual App Server process.
Those are different files with different digests, so a receipt attesting one
could never be honestly bound to the adapter launching the other -- exactly
the "schema binary != adapter binary" gap the single-binary law closes.

This script now answers all three CLI shapes the adapter and the schema
prober ever invoke:

- ``<binary> --version`` -> a fixed, obviously-synthetic version token.
- ``<binary> app-server generate-json-schema [--experimental] --out <dir>``
  -> writes one minimal, valid schema document declaring the Skill
  turn-input node (so ``supports_skill_input_path`` attests True), with
  genuinely distinct stable/experimental bytes.
- ``<binary> app-server`` (no ``generate-json-schema``/``--out``) -> the App
  Server itself: execs into ``python -m scripts.ohf.fake_app_server``,
  replacing this process's image in place (same PID, same stdio) so the
  real fake-App-Server JSON-RPC implementation serves the connection
  exactly as if it had been launched directly.
"""
import json
import os
import sys
from pathlib import Path


def main(argv: "list[str]") -> int:
    if "--version" in argv:
        sys.stdout.write("cap-s1-fixture-binary/0.0.0-synthetic\n")
        return 0
    if "--out" in argv:
        out_dir = Path(argv[argv.index("--out") + 1])
        out_dir.mkdir(parents=True, exist_ok=True)
        variant = "experimental" if "--experimental" in argv else "stable"
        doc = {
            "variant": variant,
            "$defs": {
                "SkillTurnInputItem": {
                    "type": "object",
                    "properties": {
                        "type": {"const": "skill"},
                        "name": {"type": "string"},
                        "path": {"type": "string"},
                    },
                }
            },
        }
        (out_dir / "schema.json").write_text(json.dumps(doc), encoding="utf-8")
        return 0
    # App Server passthrough: replace this process's own image with the real
    # fake-App-Server implementation. ``os.execv`` never forks -- the PID the
    # caller observed via ``subprocess.Popen`` stays identical, and stdin/
    # stdout/stderr are inherited unchanged, so the adapter's own PID/process-
    # group identity checks and the JSON-RPC stdio transport are unaffected.
    os.execv(sys.executable, [sys.executable, "-m", "scripts.ohf.fake_app_server"])
    return 0  # pragma: no cover -- os.execv never returns on success


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

"""Explicit private-home preparation/readiness; never switches or selects accounts."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from control_plane.codex_account_environment import (
    CodexAccountError, native_codex_account_scope, probe_native_account,
)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider-home", required=True, type=Path)
    sub = parser.add_subparsers(dest="command", required=True)
    seed = sub.add_parser("seed-once", help="Requires prior exclusive refresh-stream custody")
    seed.add_argument("--seed-file", required=True, type=Path)
    probe = sub.add_parser("readiness")
    probe.add_argument("--binary", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        with native_codex_account_scope(args.provider_home) as environment:
            result = ({"state": environment.seed_if_missing(args.seed_file)}
                      if args.command == "seed-once"
                      else probe_native_account(environment, args.binary))
        print(json.dumps(result, sort_keys=True, allow_nan=False))
        return 0 if result["state"] in {"NATIVE_READS_COMPLETED", "SEEDED_ONCE",
            "PRESERVED_EXISTING", "PRESERVED_CONCURRENT_PUBLICATION"} else 2
    except (CodexAccountError, OSError):
        print(json.dumps({"state": "ACCOUNT_ENVIRONMENT_REFUSED"}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

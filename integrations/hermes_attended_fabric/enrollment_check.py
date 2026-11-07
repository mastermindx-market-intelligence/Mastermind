"""Bounded read-only native enrollment/evidence check for the existing facade."""
from __future__ import annotations

import json
import site
import sys
from pathlib import Path


def main() -> int:
    try:
        if len(sys.argv) != 3:
            raise ValueError()
        source, home = (Path(value) for value in sys.argv[1:])
        if (not source.is_absolute() or not home.is_absolute()
                or not source.is_dir() or not home.is_dir()):
            raise ValueError()
        # Read the already committed dependency selection; do not invoke
        # native bootstrap, recovery, install, reload or provider resolution.
        sys.path.insert(0, str(source))
        from pm.environments import committed_venv, site_packages
        environment = committed_venv(source)
        if environment is None:
            raise ValueError()
        site.addsitedir(str(site_packages(environment)))
        sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
        from hermes_constants import set_hermes_home_override, reset_hermes_home_override
        from integrations.hermes_attended_fabric.native_evidence import (
            read_enrollment, verify_origin,
        )
        raw = sys.stdin.buffer.read(65537)
        if len(raw) > 65536:
            raise ValueError()
        request = json.loads(raw)
        if type(request) is not dict or set(request) != {"action", "arguments"}:
            raise ValueError()
        token = set_hermes_home_override(str(home))
        try:
            contract = read_enrollment(home)
            if request["action"] != "fabric_capabilities":
                verify_origin(home, request["action"], request["arguments"], contract)
            # Configuration revocation also applies after a native DB read.
            if read_enrollment(home) != contract:
                raise ValueError()
        finally:
            reset_hermes_home_override(token)
        print(json.dumps({"schema": "mastermind.hermes_origin_check.v1",
                          "authorized": True, "contract": contract},
                         separators=(",", ":")))
        return 0
    except Exception:
        # No exception text, file paths, packets, history, tokens or stderr.
        print('{"schema":"mastermind.hermes_origin_check.v1","authorized":false}')
        return 0


if __name__ == "__main__":
    raise SystemExit(main())

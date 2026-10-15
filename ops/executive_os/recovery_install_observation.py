"""Fixed installer absence readback. No service or recovery effects."""
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from control_plane.executive_recovery_host_observation import (
    HostObservationError, _wait_installer_unloaded,
)


def main(argv):
    if len(argv) != 1:
        return 64
    try:
        _wait_installer_unloaded(argv[0], deadline_monotonic_ns=time.monotonic_ns() + 20_000_000_000)
    except HostObservationError as error:
        print(error.code, file=sys.stderr)
        return 65
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

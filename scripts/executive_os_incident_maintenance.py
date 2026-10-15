#!/usr/bin/env python3
"""Closed root service-maintenance entry; never calls the recovery operation."""
import json
from pathlib import Path
import sys

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from control_plane.executive_incident_maintenance import BrokerMaintenanceError, _stop_incident_broker


def main(argv=None):
    if (sys.argv[1:] if argv is None else argv):
        sys.stderr.write("BROKER_MAINTENANCE_ARGUMENTS_REFUSED\n")
        return 64
    try:
        report = _stop_incident_broker()
    except BrokerMaintenanceError as error:
        print(json.dumps({"maintenance_state": "REFUSED",
                          "disable_attempted": error.disable_attempted,
                          "bootout_attempted": error.bootout_attempted,
                          "origin_custody": False, "provider_called": False,
                          "error": {"code": error.code}}, sort_keys=True))
        return 75 if error.disable_attempted or error.bootout_attempted else 65
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

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
                          "socket_retirement_attempted": error.socket_retirement_attempted,
                          "origin_custody": False, "provider_called": False,
                          "error": {"code": error.code}}, sort_keys=True))
        return 75 if (error.disable_attempted or error.bootout_attempted
                      or error.socket_retirement_attempted) else 65
    if (type(report) is not dict or
            report.get("maintenance_state") != "BROKER_STOPPED_OBSERVED" or
            any(type(report.get(key)) is not bool for key in (
                "disable_attempted", "bootout_attempted", "socket_retirement_attempted",
                "origin_custody", "provider_called")) or
            report["origin_custody"] or report["provider_called"]):
        # The operation already returned: a malformed report is uncertainty,
        # never evidence that no modifying command was attempted.
        print(json.dumps({"maintenance_state": "REFUSED",
                          "disable_attempted": None, "bootout_attempted": None,
                          "socket_retirement_attempted": None,
                          "origin_custody": False, "provider_called": None,
                          "error": {"code": "BROKER_MAINTENANCE_REPORT_UNPROVEN"}},
                         sort_keys=True))
        return 75
    # Publish only fixed states and exact booleans. Private source/configuration
    # metadata remains internal; the selected release is bound by host evidence.
    print(json.dumps({"maintenance_state": "BROKER_STOPPED_OBSERVED",
                      "disable_attempted": report["disable_attempted"] is True,
                      "bootout_attempted": report["bootout_attempted"] is True,
                      "socket_retirement_attempted": report["socket_retirement_attempted"] is True,
                      "origin_custody": False, "provider_called": False},
                     sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

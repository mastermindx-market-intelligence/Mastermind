#!/usr/bin/env python3
"""Closed foreground entry; dormant source policy refuses before host effects."""
import dataclasses
import json
from pathlib import Path
import sys

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from control_plane.executive_incident_composition import _ForegroundRunError, _run_foreground_forward


def main(argv=None):
    if (sys.argv[1:] if argv is None else argv):
        sys.stderr.write('FORWARD_ARGUMENTS_REFUSED\n')
        return 64
    report = {'schema': 'mastermind.incident_forward_foreground.v1',
              'original_status': 'EFFECT_UNKNOWN', 'retry_authorized': False}
    try:
        result = _run_foreground_forward()
    except _ForegroundRunError as error:
        report.update(forward_state='UNKNOWN_RETAINED' if error.pump_entered else 'NOT_SUBMITTED',
                      bootstrap_attempted=error.bootstrap_attempted,
                      bootstrapped=error.bootstrapped, child_born=error.child_born,
                      error={'code': error.code})
        print(json.dumps(report, sort_keys=True))
        return 75 if error.bootstrap_attempted or error.pump_entered else 65
    report.update(forward_state=result.classification, result=dataclasses.asdict(result))
    print(json.dumps(report, sort_keys=True))
    return 0 if result.classification == 'SUCCEEDED' else 75 if result.classification == 'UNKNOWN_RETAINED' else 65


if __name__ == '__main__':
    raise SystemExit(main())

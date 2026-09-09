"""One existing-binding census consumer. Source-only; does not enroll or install."""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import secrets
import sys

# Direct invocation and module invocation use the same repository implementation.
if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from control_plane import surface_bindings
from integrations.chairman_surfaces import web_sol_client, web_sol_census_protocol


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bindings', required=True)
    parser.add_argument('--binding-id', required=True)
    parser.add_argument('--json', action='store_true', required=True)
    args = parser.parse_args(argv)
    document, problems = surface_bindings.load_bindings(args.bindings)
    rows = [] if document is None or problems else [
        row for row in document['bindings'] if row['binding_id'] == args.binding_id]
    if len(rows) != 1:
        print(json.dumps({'status': 'UNAVAILABLE', 'code': 'invalid_binding'}))
        return 2
    now = datetime.now(timezone.utc)
    try:
        value = web_sol_client.census_via_extension(rows[0],
            operation_key='web-sol-census-'+secrets.token_hex(16), nonce=secrets.token_urlsafe(24),
            issued_at=now.isoformat(timespec='milliseconds').replace('+00:00','Z'),
            expires_at=(now+timedelta(seconds=10)).isoformat(timespec='milliseconds').replace('+00:00','Z'))
        value = web_sol_census_protocol.validate_census_receipt(value)
    except web_sol_client.WebSolExtensionError:
        print(json.dumps({'status': 'UNAVAILABLE', 'code': 'census_unavailable'}))
        return 2
    print(json.dumps(value, separators=(',', ':'), ensure_ascii=False, allow_nan=False))
    return 0 if value['status'] == 'COLLECTED' else 2


if __name__ == '__main__':
    raise SystemExit(main())

"""Isolated CLI fixture for facade tests. Never routes, contacts a provider or uses a real ledger."""
import argparse
import json
import os
from pathlib import Path
import sys

root = Path(os.environ['FABRIC_FIXTURE_STATE'])
root.mkdir(exist_ok=True)
parser = argparse.ArgumentParser()
parser.add_argument('action', choices=['status', 'request', 'result', 'accept', 'wait'])
parser.add_argument('run_id', nargs='?')
parser.add_argument('--id')
parser.add_argument('--class', dest='task_class')
parser.add_argument('--task-complexity')
parser.add_argument('--cwd')
parser.add_argument('--root')
parser.add_argument('--parent')
parser.add_argument('--stdin', action='store_true')
parser.add_argument('--by')
parser.add_argument('--max-bytes', type=int, default=8192)
parser.add_argument('--timeout')
parser.add_argument('--interval')
args = parser.parse_args()
rid = args.id or args.run_id
path = root / (rid + '.json')
empty = dict(schema='mastermind.fabric_task_status.v1', run_id=rid, root_id=None,
             parent_run_id=None, state='NOT_FOUND', result_available=False,
             result_bytes=None, accepted=None, accepted_by=None)
if args.action == 'request':
    packet = sys.stdin.read()
    data = b'RETURN: VERIFIED\n\n'
    if os.environ.get('FABRIC_FIXTURE_RESULT_BYTES'):
        size = int(os.environ['FABRIC_FIXTURE_RESULT_BYTES'])
        prefix = b'SYNTHETIC RESULT\n'
        if size < len(prefix) or size > 8_388_608:
            raise ValueError('invalid synthetic fixture size')
        data = prefix + b'R' * (size - len(prefix))
    status = dict(empty, root_id=args.root, parent_run_id=args.parent, state='DONE',
                  result_available=True, result_bytes=len(data), accepted=False)
    with path.open('x') as stream:
        json.dump(status, stream)
    (root / (rid + '.packet')).write_text(packet)
    (root / (rid + '.result')).write_bytes(data)
    print(json.dumps(status))
elif args.action in ('status', 'wait'):
    print(path.read_text() if path.exists() else json.dumps(empty))
elif args.action == 'result':
    data = (root / (rid + '.result')).read_bytes()
    if len(data) > args.max_bytes:
        sys.exit(2)
    sys.stdout.buffer.write(data)
else:
    status = json.loads(path.read_text())
    status['accepted'] = True
    status['accepted_by'] = args.by
    path.write_text(json.dumps(status))
    print(json.dumps({'accepted': True}))

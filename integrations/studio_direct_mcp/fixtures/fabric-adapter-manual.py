"""Provider-free CLI fixture for the strict manual MCP HTTP path.

Models, hosts, pool and terminal results here are synthetic. It never imports
Fabric's real picker, starts a worker, obtains a credential or touches live state.
"""
import argparse
import json
import os
from pathlib import Path
import sys

root = Path(os.environ['FABRIC_FIXTURE_STATE'])
root.mkdir(exist_ok=True)
parser = argparse.ArgumentParser()
parser.add_argument('action', choices=['status', 'request', 'result', 'accept', 'wait', 'preview'])
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
parser.add_argument('--pool')
parser.add_argument('--model', dest='requested_model')
parser.add_argument('--subject-pool')
parser.add_argument('--escalation-reason')
parser.add_argument('--max-turns', type=int)
parser.add_argument('--strict-manual-pin', action='store_true')
parser.add_argument('--quota-fallback', action='store_true')
parser.add_argument('--follow', action='store_true')
args = parser.parse_args()
rid = args.id or args.run_id
if not rid or not rid.replace('-', '').replace('_', '').isalnum():
    parser.error('synthetic run ID required')
path = root / (rid + '.json')
empty = dict(schema='mastermind.fabric_task_status.v1', run_id=rid,
             root_id=None, parent_run_id=None, state='NOT_FOUND',
             result_available=False, result_bytes=None, accepted=None, accepted_by=None)
if args.action == 'preview':
    if args.pool != 'glm' or args.requested_model not in ('glm-5.3', 'auto'):
        raise SystemExit(78)
    # Read-only preview, intentionally no per-run file or reservation.
    print(json.dumps(dict(state='PREVIEW_ONLY', reserved=False, run_id=rid,
                          pool='glm', model='glm-5.3', mode='glm', host='synthetic-host',
                          selection_rechecked_at_request=True,
                          strict_pin_enforced_at_request=True)))
elif args.action == 'request':
    # Independently require strict policy after the prior no-effect preview.
    if (not args.strict_manual_pin or args.pool != 'glm'
        or args.requested_model != 'glm-5.3' or args.quota_fallback
        or args.task_class != 'review' or args.max_turns != 12
        or args.subject_pool != 'openai' or path.exists()):
        raise SystemExit(78)
    packet = sys.stdin.read()
    response = b'RETURN: VERIFIED\n\n'
    status = dict(empty, root_id=args.root, parent_run_id=args.parent, state='DONE',
                  result_available=True, result_bytes=len(response), accepted=False)
    with path.open('x') as stream:
        json.dump(status, stream)
    (root / (rid + '.packet')).write_text(packet)
    (root / (rid + '.result')).write_bytes(response)
    (root / (rid + '.route')).write_text(json.dumps(dict(pool=args.pool,
         model=args.requested_model, strict=args.strict_manual_pin,
         quota_fallback=args.quota_fallback, max_turns=args.max_turns,
         subject_pool=args.subject_pool, root=args.root, parent=args.parent)))
    print(json.dumps(status))
elif args.action in ('status', 'wait'):
    print(path.read_text() if path.exists() else json.dumps(empty))
elif args.action == 'result':
    value=(root / (rid + '.result')).read_bytes()
    if len(value)>args.max_bytes:
        raise SystemExit(78)
    sys.stdout.buffer.write(value)
else:
    status=json.loads(path.read_text())
    status['accepted']=True
    status['accepted_by']=args.by
    path.write_text(json.dumps(status))
    print(json.dumps(dict(accepted=True)))

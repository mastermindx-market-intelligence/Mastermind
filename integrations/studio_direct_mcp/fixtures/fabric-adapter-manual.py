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
parser.add_argument('--experiential-retention-acknowledged', action='store_true')
parser.add_argument('--experiential-sensitive-data-opt-in', action='store_true')
parser.add_argument('--experiential-proprietary-code', action='store_true')
parser.add_argument('--experiential-code-exposure-opt-in', action='store_true')
parser.add_argument('--experiential-response-only', action='store_true')
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
included = ['deepseek-v4.1-flash', 'deepseek-v4.1-flash-1017', 'gpt-6-luna',
            'clef', 'clef-flash', 'jev-latest', 'gpt-6-luna-decisions']
paid = ['deepseek-v4.1-flash-uncensored', 'glm-5.3-flash-uncensored']
exp_models = ['glm-5.3-uncensored', *included, *paid]
consent = all((args.experiential_retention_acknowledged, args.experiential_sensitive_data_opt_in,
               args.experiential_proprietary_code, args.experiential_code_exposure_opt_in))
if args.action == 'preview':
    if args.pool == 'glm' and args.requested_model in ('glm-5.3', 'auto'):
        model, mode = 'glm-5.3', 'glm'
    elif args.pool == 'byteplus' and args.requested_model in (None, 'deepseek-v4.1-flash', 'glm-5.3-flash'):
        model, mode = args.requested_model or 'glm-5.3-flash', 'byteplus'
    elif args.pool == 'experiential' and args.requested_model in (*exp_models, 'free', 'uncensored'):
        model = included[0] if args.requested_model == 'free' else paid[0] if args.requested_model == 'uncensored' else args.requested_model
        mode = 'experiential'
    else:
        raise SystemExit(78)
    # Read-only preview, intentionally no per-run file or reservation.
    # This is a synthetic route, not native admission or provider entitlement.
    print(json.dumps(dict(state='PREVIEW_ONLY', reserved=False, run_id=rid,
                          pool=args.pool, model=model, mode=mode, host='synthetic-host',
                          selection_rechecked_at_request=True,
                          strict_pin_enforced_at_request=True)))
elif args.action == 'request':
    # Independently require strict policy after the prior no-effect preview.
    # The Experiential branch is a provider-free fixture only.
    auto_response = args.pool is None and args.requested_model is None and args.experiential_response_only and consent
    if (not args.strict_manual_pin and not auto_response) or args.quota_fallback or path.exists():
        raise SystemExit(78)
    if args.pool == 'glm':
        if (args.requested_model != 'glm-5.3' or args.task_class != 'review'
            or args.max_turns != 12 or args.subject_pool != 'openai'):
            raise SystemExit(78)
    elif args.pool == 'byteplus':
        if (args.requested_model not in ('deepseek-v4.1-flash', 'glm-5.3-flash')
            or args.task_class != 'mechanical' or args.max_turns not in (None, 8)):
            raise SystemExit(78)
    elif args.pool == 'experiential' or auto_response:
        if ((not auto_response and args.requested_model not in exp_models)
            or args.task_class != 'mechanical' or args.max_turns is not None
            or args.subject_pool is not None
            or not args.experiential_retention_acknowledged
            or not args.experiential_sensitive_data_opt_in
            or not args.experiential_proprietary_code
            or not args.experiential_code_exposure_opt_in):
            raise SystemExit(78)
    else:
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
         subject_pool=args.subject_pool, root=args.root, parent=args.parent,
         **(dict(
             experiential_retention_acknowledged=args.experiential_retention_acknowledged,
             experiential_sensitive_data_opt_in=args.experiential_sensitive_data_opt_in,
             experiential_proprietary_code=args.experiential_proprietary_code,
             experiential_code_exposure_opt_in=args.experiential_code_exposure_opt_in,
         ) if args.pool == 'experiential' or auto_response else {}),
         **({'response_only': True} if args.experiential_response_only else {}))))
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

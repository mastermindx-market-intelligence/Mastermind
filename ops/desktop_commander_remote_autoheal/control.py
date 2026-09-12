#!/usr/bin/python3
"""Local controls; status observes existing launchd/runtime truth, never mutates it."""
import datetime, json, pathlib, re, subprocess, sys
root = pathlib.Path(__file__).resolve().parent
config = json.loads((root / 'config.json').read_text())
target = 'gui/{}/{}'.format(config['uid'], config['label'])
def run(args):
    return subprocess.run(['/bin/launchctl'] + args, capture_output=True, text=True, timeout=20)
def status():
    observed = datetime.datetime.now(datetime.timezone.utc)
    s = {'service': config['label'], 'observed_at': observed.isoformat(),
         'loaded': None, 'disabled': None, 'pid': None, 'healthy': False,
         'inner_last_ok_at': None, 'reason': 'launchd_observation_unavailable'}
    code = 2
    try:
        result = run(['print', target])
        disabled = run(['print-disabled', 'gui/{}'.format(config['uid'])])
        if disabled.returncode == 0:
            match = re.search(r'"' + re.escape(config['label']) + r'"\s*=>\s*(disabled|enabled|true|false)', disabled.stdout)
            s['disabled'] = match.group(1) in ('disabled', 'true') if match else False
        if result.returncode == 113:
            s.update(loaded=False, reason='service_disabled' if s['disabled'] else 'service_unloaded')
            code = 3
        elif result.returncode == 0:
            s['loaded'] = True
            match = re.search(r'^\s*pid\s*=\s*(\d+)\s*$', result.stdout, re.M)
            s['pid'] = int(match.group(1)) if match else None
            s['reason'] = 'state_unavailable'
            state = json.loads((root / 'status.json').read_text())
            if not isinstance(state, dict):
                raise ValueError('state_unavailable')
            if (root / 'HOLD.json').exists():
                s['reason'] = 'service_held'
            elif s['pid'] is None or state.get('pid') != s['pid']:
                s['reason'] = 'generation_mismatch'
            elif state.get('phase') == 'waiting_for_incumbent':
                s['reason'] = 'waiting_for_incumbent'
            elif state.get('remoteReachable') is not True:
                s['reason'] = 'remote_unreachable'
            elif state.get('phase') != 'healthy':
                s['reason'] = 'runtime_not_healthy'
            else:
                s['reason'] = 'inner_probe_stale'
                last_ok = datetime.datetime.fromisoformat(state['innerLastOkAt'].replace('Z', '+00:00'))
                if last_ok.tzinfo is None:
                    raise ValueError('naive_probe_time')
                s['inner_last_ok_at'] = last_ok.isoformat()
                if -5 <= (observed - last_ok).total_seconds() <= 60:
                    s.update(healthy=True, reason='healthy')
                    code = 0
    except (OSError, ValueError, KeyError, TypeError, AttributeError, subprocess.SubprocessError):
        pass  # Stable observation codes only; never print source payloads or errors.
    print(json.dumps(s, indent=2))
    return code
command = sys.argv[1] if len(sys.argv) > 1 else 'status'
if command == 'status':
    raise SystemExit(status())
elif command == 'stop':
    if run(['print', target]).returncode == 0:
        result = run(['bootout', target])
        print('stop return code:', result.returncode)
        raise SystemExit(result.returncode)
elif command in ('start', 'resume'):
    if command == 'resume':
        for name in ['HOLD.json', 'restart-budget.json']:
            (root / name).unlink(missing_ok=True)
    if (root / 'HOLD.json').exists():
        print('Held: inspect HOLD.json and resolve the cause before using resume.')
        raise SystemExit(1)
    result = run(['print', target])
    action = ['kickstart', target] if result.returncode == 0 else ['bootstrap',
              'gui/{}'.format(config['uid']), config['plist']]
    result = run(action)
    print('start return code:', result.returncode)
    raise SystemExit(result.returncode)
else:
    raise SystemExit('Usage: dc-service status|start|stop|resume')

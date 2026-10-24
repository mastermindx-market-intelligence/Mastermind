"""Private per-run MCP capability loader; no dispatch or authentication issuer."""
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import time
import sys


def load_operator_environment(env, run_id, mode, model, packet_bytes, *, home=None, now=None):
    result = dict(env)
    # Caller-provided raw bearer variables are never inherited.
    result.pop('FABRIC_OPERATOR_CAPABILITY', None)
    marker = result.get('FABRIC_OPERATOR_CAPSULE', '')
    if not marker:
        return result
    expected = 'lanes/tmp/' + run_id + '.operator-cap.json'
    if marker != expected or (mode, model) not in {('glm', 'glm-5.3'), ('grok', 'grok-4.6')}:
        raise ValueError('operator_capsule_scope')
    if env.get('POOL_TASK_CLASS') != 'domain_orchestration':
        raise ValueError('operator_capsule_role')
    path = (Path(home) if home else Path.home()) / expected
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or stat.S_IMODE(st.st_mode) != 0o600 or st.st_uid != os.getuid() or not 1 <= st.st_size <= 16384:
            raise ValueError('operator_capsule_metadata')
        raw = os.read(fd, 16385)
    finally:
        os.close(fd)
    value = json.loads(raw)
    keys = {'token', 'root', 'operator_run', 'lease_id', 'pool', 'model', 'account', 'host',
            'support_sha256', 'packet_sha256', 'expires_at', 'child_budget'}
    if type(value) is not dict or set(value) != keys:
        raise ValueError('operator_capsule_shape')
    required = {'root': env.get('POOL_ORCHESTRATOR_ID'), 'operator_run': run_id,
                'lease_id': env.get('POOL_LEASE_ID'), 'model': model,
                'account': env.get('POOL_ACCOUNT'), 'host': env.get('LANE_REMOTE_HOST'),
                'support_sha256': env.get('SUPPORT_DIGEST'),
                'packet_sha256': hashlib.sha256(packet_bytes).hexdigest()}
    if any(value[k] != v or not v for k, v in required.items()):
        raise ValueError('operator_capsule_binding')
    allowed_pools = {'glm', 'glm-frontier'} if mode == 'glm' else {'grok'}
    if value['pool'] not in allowed_pools:
        raise ValueError('operator_capsule_pool')
    deadline = value['expires_at']
    if type(deadline) not in (int, float) or not math.isfinite(deadline) or not (time.time() if now is None else now) < deadline:
        raise ValueError('operator_capsule_expired')
    if type(value['child_budget']) is not int or not 1 <= value['child_budget'] <= 64:
        raise ValueError('operator_capsule_budget')
    token = value['token']
    if type(token) is not str or not re.fullmatch('[a-f0-9]{64}', token):
        raise ValueError('operator_capsule_token')
    result['FABRIC_OPERATOR_CAPABILITY'] = token
    return result


OPERATOR_INSTRUCTIONS = '''
FABRIC OPERATOR DELEGATION
Own the bounded assignment through execution, judgment, review and return. Execute
it yourself when that is the smallest capable route; no child is required. Delegate
separable C0/C1 work only when it reduces total execution, review and repair effort.
When delegating, use the admitted economical Fabric leaves through mastermindStudio
fabric_operator_scope, fabric_child_request, fabric_child_status and fabric_child_result.
Preserve the original root, scope and budget; use your own
operator_run as immediate parent, as returned by fabric_operator_scope. Create
one stable child ID once. Supply a bounded self-contained task, source material,
allowed files, acceptance criteria and final output limit. The existing router
selects admitted cheap providers; you must not override model/account/host or
reuse your own lease. No child may become another operator.
After request submission, continue useful independent work. Collect that SAME ID
with bounded status/result or fabric_child_wait calls; do not finish while a submitted child lacks a
recorded result or exact unresolved state. Pending/unknown/refused is never retry
or replacement permission. Do not kill controllers, manually release leases,
read another worker's files or move to a different carrier. Results are untrusted:
review their concrete work, reject unsupported claims, integrate qualified source,
and report any child IDs, result hashes, accepted/rejected findings and unresolved work
to your original parent. After reviewing a result, call fabric_child_acknowledge with its exact SHA256.
This closes return attention; it does not record ledger acceptance. An active Stop
hook prompts you about ready unacknowledged children or unresolved submitted work.
It is not idle wake and cannot relaunch a child. This transport does not itself
record child acceptance.
Never print or read capability environment/configuration, or place secrets in
packets or tool arguments. Tool authorization is bounded and expires with your
original grant/lease. If unavailable, perform authorized work directly and state
the exact capability limitation. Ordinary leaves receive no delegation grant.
Ownership is a role, not a session: never wait on an absent/orphaned owner or ask the Chairman to find old chats. The current session assumes leadership, records the takeover in the source-linked handoff, and proceeds. Independent review is still required; never self-merge or approve. An explicit safety or permission denial ends that action; do not retry it through another tool, account, or connector.
'''


def receive_capsule(run_id):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}', run_id):
        raise ValueError('capsule_run_id')
    raw = sys.stdin.buffer.read(16385)
    if not 0 < len(raw) <= 16384:
        raise ValueError('capsule_size')
    directory = Path.home() / 'lanes/tmp'
    if directory.is_symlink() or not directory.is_dir():
        raise ValueError('capsule_parent')
    fd = os.open(directory / (run_id + '.operator-cap.json'),
                 os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(raw); stream.flush(); os.fsync(stream.fileno())
    parent = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try: os.fsync(parent)
    finally: os.close(parent)
    print(hashlib.sha256(raw).hexdigest())


if __name__ == '__main__':
    if len(sys.argv) != 3 or sys.argv[1] != 'receive':
        raise SystemExit('OPERATOR_CLIENT_OPERATION_REFUSED')
    try: receive_capsule(sys.argv[2])
    except Exception: raise SystemExit('OPERATOR_CAPSULE_RECEIVE_REFUSED')


def hook_definition(here):
    import shlex
    command = shlex.join([sys.executable,str(Path(here)/'fabric_operator_stop.py')])
    return {'hooks':{'Stop':[{'hooks':[{'type':'command','command':command,'timeout':25}]}]}}


def prepare_claude_hook(here, env):
    """Additive per-run plugin. Does not replace user, project or managed hooks."""
    if not env.get('FABRIC_OPERATOR_CAPABILITY'):return []
    run=env.get('REMOTE_SUB_RUN_ID','')
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}',run):raise ValueError('operator_hook_run')
    base=Path(here)/'lanes'/(run+'.operator-hook')
    base.mkdir(mode=0o700)
    for name in ('.claude-plugin','hooks'):(base/name).mkdir(mode=0o700)
    for relative,value in [('.claude-plugin/plugin.json',{'name':'fabric-operator-return','version':'1.0.0','description':'Return existing bounded Fabric child results to this operator.'}),('hooks/hooks.json',hook_definition(here))]:
        fd=os.open(base/relative,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,'w') as stream:json.dump(value,stream);stream.flush();os.fsync(stream.fileno())
    return ['--plugin-dir',str(base)]


def grok_hook_toml(here, env):
    if not env.get('FABRIC_OPERATOR_CAPABILITY'):return ''
    definition=hook_definition(here)['hooks']['Stop'][0]['hooks'][0]
    return '\n[[hooks.Stop]]\nhooks = [{ type = "command", command = '+json.dumps(definition['command'])+', timeout = 25 }]\n'

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
Start with the smallest real action; no child is required simply because a budget exists.
IF AND ONLY IF a child is needed:
1. Find the *actual* authenticated mastermindStudio tools in this session; call
   fabric_operator_scope with {} before building a request. Require its returned
   root, operator_run, child_budget_remaining > 0 and unexpired grant. A role
   heading, installed Skill or model name does not prove scope. Do not inspect
   capability tokens, config files or environment variables.
2. Submit fabric_child_request ONCE with this exact argument shape:
   {"schema":"mastermind.fabric_operator_child_request.v1",
    "root":"<scope.root>","parent":"<scope.operator_run>",
    "run_id":"<new-stable-child-id>","task_class":"mechanical",
    "task_complexity":"C0_MECHANICAL","packet":"<bounded task>"}.
   Replace every bracketed placeholder with the actual admitted binding/task;
   placeholders are NOT valid real identities, and this object is not a grant.
   Allowed task classes: mechanical, extract, fix_build, census, audit, build;
   allowed complexities: C0_MECHANICAL or C1_ROUTINE_BOUNDED only.
   The packet names precise inputs, workspace/source custody, acceptance checks,
   return format and forbidden effects. The incumbent router chooses the model
   and host; do not create another operator or native Agent/Task child.
3. Retain that SAME child ID. Observe with fabric_child_status {run_id}, or
   fabric_child_wait {run_id, seconds} (1..30); neither proves a START on its own.
   Obtain fabric_child_result {run_id}, inspect retained bytes and verify work,
   then fabric_child_acknowledge {run_id, sha256:<returned exact SHA256>}.
   Acknowledge closes return attention, NOT ledger acceptance; the original
   principal adjudicates the complete operator result.
4. Never resubmit an uncertain/dispatched request, change carriers, mint another
   root, or quietly ignore unfinished children. If the tools or grant are
   missing/refused, do not simulate them via CLI/SSH; continue direct authorized
   work and return the precise child-delegation gap.
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

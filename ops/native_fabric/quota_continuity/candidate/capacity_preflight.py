"""One bounded capacity probe inside the existing admitted provider wrapper.

This request never contains the task, tools or a system prompt. Only a typed
rejection can terminate before the task CLI. No retries or credential discovery.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
import signal
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import provider_outcome as outcome

SCHEMA='mastermind.capacity_preflight.v1'
CAPACITY_RC=75
DENIED_RC=78
LIMIT=65536
TIMEOUT=20.0
PROVIDERS={'minimax','glm'}
ERROR_KINDS={(429,'rate_limit_error'):'rate_limit',
             (401,'authentication_error'):'authentication',
             (403,'permission_error'):'permission',
             (402,'billing_error'):'billing'}
# Numeric vendor codes take precedence over a compatibility layer's generic
# error type. GLM uses HTTP 429 for account restrictions as well as capacity.
# Sources: docs.z.ai/api-reference/api-code and
# platform.minimax.io/docs/api-reference/errorcode (checked 2026-10-18).
VENDOR_CODES={
    'glm':{'1000':'authentication','1001':'authentication','1003':'authentication',
           '1005':'authentication','1113':'billing','1220':'permission',
           '1301':'permission','1302':'rate_limit','1305':'provider_error',
           '1308':'quota_exhausted','1309':'billing','1310':'quota_exhausted',
           '1311':'permission','1313':'permission','1314':'billing','1315':'permission',
           '1316':'billing','1317':'billing','1318':'budget_limit',
           '1319':'budget_limit','1320':'budget_limit','1321':'budget_limit'},
    'minimax':{'1002':'rate_limit','1004':'authentication','1008':'billing',
               '1026':'permission','1027':'permission','2049':'authentication',
               '2056':'quota_exhausted'},
}

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None


def payload(model):
    return json.dumps({'model':model,'max_tokens':1,'stream':False,
        'messages':[{'role':'user','content':'Reply with one dot.'}]},
        sort_keys=True,separators=(',',':')).encode()


def classify_error(provider,status,error):
    """Typed HTTP/API fields only; never extract codes or limits from prose."""
    if not isinstance(error,dict) or type(status) is not int:return None
    code=error.get('code')
    if code is not None:
        if type(code) is int:code=str(code)
        if not isinstance(code,str) or not code.isdigit():return None
        kind=VENDOR_CODES.get(provider,{}).get(code)
        if kind in outcome.CAPACITY:return kind if status==429 else None
        return kind if 400<=status<500 else None
    typ=error.get('type')
    return ERROR_KINDS.get((status,typ)) if isinstance(typ,str) else None


def _timeout(signum,frame):
    raise TimeoutError('capacity_probe_deadline')


def check(env,provider,model,owner_path):
    """Return a typed terminal observation or None to proceed with original CLI."""
    if env.get('POOL_CAPACITY_PREFLIGHT')!='1':return None
    if provider not in PROVIDERS or env.get('FABRIC_OPERATOR_CAPABILITY'):
        return None
    # Scope validation precedes network activity. No key lookup or task read.
    outcome.bound_outcome({},env,provider,model)
    base=env.get('ANTHROPIC_BASE_URL','')
    parsed=urllib.parse.urlsplit(base)
    if (parsed.scheme not in {'https','http'} or not parsed.netloc or parsed.username
            or parsed.password or parsed.query or parsed.fragment):
        print('CAPACITY_PREFLIGHT_INDETERMINATE reason=endpoint',file=sys.stderr)
        return None
    token=env.get('ANTHROPIC_AUTH_TOKEN')
    api_key=env.get('ANTHROPIC_API_KEY')
    if not token and not api_key:return None
    support=env.get('SUPPORT_DIGEST','')
    if len(support)!=64 or any(c not in '0123456789abcdef' for c in support):
        return None
    # Preserve any existing caller timer; do not replace a lifecycle owner's fuse.
    if signal.getitimer(signal.ITIMER_REAL)!=(0.0,0.0):return None
    wire=base.rstrip('/')+'/v1/messages'
    body=payload(model)
    headers={'Content-Type':'application/json','anthropic-version':'2023-06-01'}
    headers['Authorization' if token else 'x-api-key']='Bearer '+token if token else api_key
    request=urllib.request.Request(wire,data=body,headers=headers,method='POST')
    old=signal.signal(signal.SIGALRM,_timeout)
    start=time.monotonic()
    status,raw,retry_after=None,b'',None
    try:
        signal.setitimer(signal.ITIMER_REAL,TIMEOUT)
        opener=urllib.request.build_opener(NoRedirect())
        try:
            response=opener.open(request,timeout=TIMEOUT)
        except urllib.error.HTTPError as exc:
            response=exc
        with response:
            status=response.code
            raw=response.read(LIMIT+1)
            retry_after=response.headers.get('Retry-After')
        if len(raw)>LIMIT:return None
        value=json.loads(raw)
        error=value.get('error') if isinstance(value,dict) else None
        typ=error.get('type') if isinstance(error,dict) else None
        kind=classify_error(provider,status,error)
        if kind is None or kind=='provider_error':
            print('CAPACITY_PREFLIGHT_PROCEED status='+str(status),file=sys.stderr)
            return None
        reset=None
        if kind in outcome.CAPACITY and isinstance(retry_after,str) and retry_after.isdigit():
            delay=int(retry_after)
            if 0<delay<=32*86400:reset=time.time()+delay
        rc=CAPACITY_RC if kind in outcome.CAPACITY else DENIED_RC
        owner=Path(owner_path)
        evidence=dict(schema=SCHEMA,task_cli_started=False,
            endpoint_sha256=outcome.digest(wire.encode()),request_sha256=outcome.digest(body),
            response_sha256=outcome.digest(raw),response_bytes=len(raw),
            error_type=typ,error_code=str(error['code']) if error.get('code') is not None else None,
            api_status=status,support_digest=support,
            control_flow_owner=owner.name,control_flow_sha256=outcome.digest(outcome.regular_bytes(owner,1048576)),
            helper_sha256=outcome.digest(outcome.regular_bytes(Path(__file__),1048576)),
            elapsed_seconds=round(time.monotonic()-start,4),attempts=1)
        return outcome.bound_outcome(dict(kind=kind,command_rc=rc,
            initial_rejection=kind in outcome.CAPACITY,complete_event_capture=False,
            api_status=status,reset_at=reset,reset_source='provider_event' if reset else None,
            session_id=None,capture_sha256=outcome.digest(b''),capture_bytes=0,
            stdout_sha256=outcome.digest(b''),pre_task_evidence=evidence),env,provider,model)
    except (OSError,ValueError,TypeError,urllib.error.URLError):
        print('CAPACITY_PREFLIGHT_INDETERMINATE',file=sys.stderr)
        return None
    finally:
        signal.setitimer(signal.ITIMER_REAL,0)
        signal.signal(signal.SIGALRM,old)


def stop_before_task(value,env):
    """Caller MUST immediately return this rc instead of launching the task CLI."""
    target=Path(env['POOL_OUTCOME_FILE']).with_suffix('.preflight.json')
    outcome.write_new(target,value)
    print('CAPACITY_PREFLIGHT_TASK_NOT_STARTED kind='+value['kind'],file=sys.stderr)
    return value['command_rc']


def reserve_task_start(env):
    if env.get('POOL_CAPACITY_PREFLIGHT')=='1':
        target=Path(env['POOL_OUTCOME_FILE']).with_suffix('.task-cli-started.json')
        outcome.write_new(target,dict(schema='mastermind.task_cli_start_reserved.v1',
            run_id=env['REMOTE_SUB_RUN_ID'],reserved_at=time.time()))


def main(args):
    if len(args)!=2 or args[0] not in PROVIDERS:return DENIED_RC
    value=check(os.environ,args[0],args[1],Path(__file__).with_name('sub.sh'))
    if value is not None:return stop_before_task(value,os.environ)
    reserve_task_start(os.environ)
    return 0

if __name__=='__main__':
    try:raise SystemExit(main(sys.argv[1:]))
    except (OSError,ValueError,KeyError):
        print('CAPACITY_PREFLIGHT_LOCAL_REFUSAL',file=sys.stderr);raise SystemExit(DENIED_RC)

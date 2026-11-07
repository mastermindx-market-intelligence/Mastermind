"""Fresh fixture PRIMARY facts only; never render outputs or settle a process."""
import json
import math
import os
from pathlib import Path

from scripts.ci_pytest_timing import _h1_failure_metadata, _h1_metadata_is_safe

MODULE='tests/test_paid_provider_entry_linux.py'
CANARY=b'0123456789abcdef0123456789abcdef'
PREFIXES=frozenset(('CANONICAL_PAID_CONTEXT_REFUSED','REMOTE_SUB_COMMISSION_BUDGET_INVALID',
    'REMOTE_SUB_LANE_ROOT_REFUSED','REMOTE_SUB_PACKET_MISSING','REMOTE_SUB_PACKET_UNREADABLE',
    'ARTIFACT_DELIVERY_CONTRACT_REFUSED','REMOTE_SUB_CWD_REFUSED','REMOTE_SUB_CWD_MISSING',
    'REMOTE_SUB_CWD_UNREADABLE','REMOTE_SUB_PREFLIGHT_REFUSED','CANONICAL_PAID_SUPPORT_REFUSED',
    'REMOTE_SUB_ADMISSION_REFUSED','REMOTE_SUB_ADMISSION_ERROR','REMOTE_SUB_COMMISSION_TIME_EXHAUSTED',
    'CANONICAL_PAID_PREFLIGHT_REFUSED','CANONICAL_PAID_ARTIFACT_REFUSED'))


# Diagnostic bounds only. These values never admit work or settle a process.
ADMISSION_REASONS=frozenset((
    'reconciliation_hold_present','lane_key_already_active',
    'active_lane_limit_reached','host_load_at_or_above_limit',
    'host_memory_unknown','host_memory_below_floor',
    'host_temperature_unknown','host_temperature_at_or_above_limit',
    'host_disk_unknown','host_disk_volume_mismatch','host_disk_below_staging_reserve'))
_ADMISSION_NUMBERS=frozenset(('active_count','legacy_count','json_locked_count',
    'max_active','load1','cpu_count','load_ratio_limit'))
_ADMISSION_FACTS=_ADMISSION_NUMBERS|{'reasons'}
_ADMISSION_SNAPSHOT=_ADMISSION_FACTS|{'allowed','stale_reaped'}
_STATE_KEYS=frozenset(('returncode','timed_out','receipt_state','refusal_prefix'))


def _admission_is_safe(value):
    if type(value)is not dict or set(value)!=_ADMISSION_FACTS:return False
    reasons=value['reasons']
    if (type(reasons)is not list or not 1<=len(reasons)<=len(ADMISSION_REASONS)
            or not all(type(reason)is str and reason in ADMISSION_REASONS for reason in reasons)
            or len(set(reasons))!=len(reasons)):return False
    for key in ('active_count','legacy_count','json_locked_count'):
        if type(value[key])is not int or not 0<=value[key]<=65535:return False
    if type(value['cpu_count'])is not int or not 1<=value['cpu_count']<=65535:return False
    if (type(value['max_active'])is not int
            or not 1<=value['max_active']<=min(32,value['cpu_count'])):return False
    for key,upper in (('load1',65535),('load_ratio_limit',1.5)):
        number=value[key]
        if (type(number)not in (int,float) or not 0<=number<=upper
                or not math.isfinite(number)):return False
    return value['load_ratio_limit']>0


def _unique_json_fields(pairs):
    value={}
    for key,item in pairs:
        if key in value:raise ValueError('duplicate admission field')
        value[key]=item
    return value


def _reject_json_constant(_value):
    raise ValueError('nonfinite admission value')


def admission_facts(raw,returncode,timed_out):
    """Return only closed diagnostic quantities from one qualified refusal."""
    if (type(returncode)is not int or returncode!=75 or timed_out is not False
            or refusal_prefix(raw)!='REMOTE_SUB_ADMISSION_REFUSED'):return None
    first=raw.split(b'\n',1)[0]
    prefix=b'REMOTE_SUB_ADMISSION_REFUSED '
    if len(first)>4096 or not first.startswith(prefix):return None
    try:
        value=json.loads(first[len(prefix):],object_pairs_hook=_unique_json_fields,
            parse_constant=_reject_json_constant)
        if (type(value)is not dict or set(value)!=_ADMISSION_SNAPSHOT
                or value['allowed']is not False):return None
        stale=value['stale_reaped']
        if (type(stale)is not list or len(stale)>128
                or not all(type(label)is str and len(label)<=256 for label in stale)):return None
        # Private stale labels are neither rendered nor hashed.
        facts={key:value[key] for key in _ADMISSION_FACTS}
        return facts if _admission_is_safe(facts) else None
    except (ValueError,TypeError,OverflowError,RecursionError):
        return None


def refusal_prefix(raw):
    if (type(raw)is not bytes or len(raw)>4*1024*1024 or CANARY in raw
            or any(byte not in (9,10,13)and not 32<=byte<=126 for byte in raw)):
        return 'UNKNOWN'
    first=raw.split(b'\n',1)[0]
    for name in PREFIXES:
        prefix=name.encode('ascii')
        if first==prefix or first.startswith(prefix+b' '):return name
    return 'UNKNOWN'


def failure_state(error,executed,raw):
    code=getattr(executed,'returncode',None);timeout=getattr(executed,'timed_out',None)
    value=dict(returncode=code if type(code)is int and -255<=code<=255 else None,
        timed_out=timeout if type(timeout)is bool else None,
        receipt_state='UNKNOWN',refusal_prefix=refusal_prefix(raw))
    admission=admission_facts(raw,code,timeout)
    if admission is not None:value['admission']=admission
    # This raw local was already read through _fixture_owned_bytes. Never
    # inspect another frame/local or print any of its bytes.
    expected=str(Path(__file__).with_name('test_paid_provider_entry_linux.py').absolute())
    trace=error.__traceback__
    for _ in range(32):
        if trace is None:break
        frame=trace.tb_frame
        if (os.path.abspath(frame.f_code.co_filename)==expected
                and frame.f_code.co_name=='_fixture_model_settled' and 'raw'in frame.f_locals):
            receipt=frame.f_locals['raw']
            if receipt is None:value['receipt_state']='ABSENT'
            elif type(receipt)is bytes and CANARY not in receipt:value['receipt_state']='PRESENT'
        trace=trace.tb_next
    return value


def failure_notice(request,error,executed,raw):
    try:
        source=_h1_failure_metadata(request.node.nodeid,'call',error=error)
        state=failure_state(error,executed,raw)
        if not _h1_metadata_is_safe(source) or source['module']!=MODULE:return
        if (type(state)is not dict or set(state)not in (_STATE_KEYS,_STATE_KEYS|{'admission'})
                or state['returncode']is not None and not(type(state['returncode'])is int and -255<=state['returncode']<=255)
                or state['timed_out']is not None and type(state['timed_out'])is not bool
                or state['receipt_state']not in ('UNKNOWN','ABSENT','PRESENT')
                or state['refusal_prefix']not in PREFIXES|{'UNKNOWN'}):return
        if 'admission'in state and (state['returncode']!=75 or state['timed_out']is not False
                or state['refusal_prefix']!='REMOTE_SUB_ADMISSION_REFUSED'
                or not _admission_is_safe(state['admission'])):
            state={key:state[key] for key in _STATE_KEYS}
        reporter=request.config.pluginmanager.getplugin('terminalreporter')
        if reporter is not None:
            with request.getfixturevalue('capsys').disabled():
                reporter.write_line('\n::error file='+MODULE+',title=H1 provider PRIMARY diagnostic::'
                    +json.dumps(dict(stage='PRIMARY',source=source,**state),sort_keys=True,separators=(',',':')))
    except Exception:
        pass  # Diagnostics never replace the original failure or cleanup.

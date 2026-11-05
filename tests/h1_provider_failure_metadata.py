"""Fresh fixture PRIMARY facts only; never render outputs or settle a process."""
import json
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
        if (set(state)!={'returncode','timed_out','receipt_state','refusal_prefix'}
                or state['returncode']is not None and not(type(state['returncode'])is int and -255<=state['returncode']<=255)
                or state['timed_out']is not None and type(state['timed_out'])is not bool
                or state['receipt_state']not in ('UNKNOWN','ABSENT','PRESENT')
                or state['refusal_prefix']not in PREFIXES|{'UNKNOWN'}):return
        reporter=request.config.pluginmanager.getplugin('terminalreporter')
        if reporter is not None:
            with request.getfixturevalue('capsys').disabled():
                reporter.write_line('\n::error file='+MODULE+',title=H1 provider PRIMARY diagnostic::'
                    +json.dumps(dict(stage='PRIMARY',source=source,**state),sort_keys=True,separators=(',',':')))
    except Exception:
        pass  # Diagnostics never replace the original failure or cleanup.

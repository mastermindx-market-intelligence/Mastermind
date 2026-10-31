"""INTERMEDIATE fixture-only terminal reporter; never original-program proof.

The caller supplies the fixed compiler output over held source. Only the outer
bootstrap's final Exception handler gets a report hook; all actual held modules
remain unchanged. The hook reports the exception object that handler really
caught. A finite return trace records the actual remote _execute nonzero return
line, used only when the whole diagnostic exits nonzero without a terminal
exception. Handled control-flow exceptions are neither sampled nor called causes.
"""
import ast
import json

from tests import h1_bootstrap_diagnostic as original

SCOPE = 'INTERMEDIATE_ONLY'
MAX_BYTES = 4096
KEYS = frozenset(('scope','event','module','function','line','type'))
EVENTS = frozenset(('HANDLED_TERMINAL_EXCEPTION','ESCAPING_TERMINAL_EXCEPTION',
    'TERMINAL_RETURN_NONZERO','DIAGNOSTIC_COMPLETED','REPORTER_FAILURE'))
PUBLIC = {
    'paid_provider_entry': ('_bootstrap_main','_run_executor','_support_imports',
        'request','check','refuse','validate_request','request_from_capsule',
        'model_command','_load_initializer','_run_model_entry','__exit__'),
    'remote_sub_exec': ('main','_execute','_canonical_model_command','_fail','_bound_lane_packet'),
    'paid_model_owner': ('canonical_state_ext','launch_observer','directory','read'),
    'paid_glm_model_client': ('private_input','parse','validate_body','execute'),
    'lane_runtime': ('load_runtime_config','parse_bounded_seconds','acquire',
        '_append_process_receipt','run_owned_process','install_signal_cleanup',
        'cleanup_receipt_is_proven'),
    'fabric_policy_snapshot': ('parse_policy','critical_fingerprint','compatible',
        'verify_for_admission','verified_snapshot_path','policy_lock','bounded_file'),
    'paid_yaml_runtime': ('held_yaml','_owner','_finder_check','__enter__','__exit__',
        '_held_provenance','_held_member_table','_reject_held_ambient','find_spec','exec_module'),
    'linux_process_identity': ('inspect_linux_process_image',),
    'artifact_delivery': ('validate_remote_lane_layout','open_remote_lane_outputs'),
    '<fixed-paid-entry>': ('_bootstrap_main','<module>'),
}
TYPES = original.EXCEPTIONS | frozenset(('FileNotFoundError','PermissionError',
    'NotADirectoryError','IsADirectoryError','TimeoutError','ImportError','ModuleNotFoundError',
    'ModelOnlyRefused','LaneRuntimeError','LaneRuntimeConfigError','LaneAdmissionRefused',
    'OwnedProcessStartError','ProcessCensusError','InitializerCommitmentRefused',
    'TokenDataRefused','NestedDataRefused','UNKNOWN','NONZERO_RETURN','NO_TERMINAL_REFUSAL'))
_ANCHOR = ('    except Exception:\n'
    '        # No exception/raw command, environment, capability or provider prose.\n'
    '        return 78\n')
_REPLACEMENT = ('    except Exception as _h1_terminal_error:\n'
    '        _h1_terminal(_h1_terminal_error)\n'
    '        return 78\n')


def build_variant(program,here):
    # Reuse shape validation, not an ambient loader or a source authority.
    original.build_probe(program,here)
    rest=program[len(original._PROGRAM_PREFIX):]
    chunk=rest[len(original._PROGRAM_ENTRY):len(rest)-len(original._PROGRAM_TAIL)]
    source=ast.literal_eval(chunk)
    if source.count(_ANCHOR)!=1:
        raise ValueError('terminal_variant_shape_refused')
    source=source.replace(_ANCHOR,_REPLACEMENT,1)
    entry=original._PROGRAM_ENTRY.replace(
        "_entry={'__name__':'_fixed_paid_entry'}",
        "_entry={'__name__':'_fixed_paid_entry','_h1_terminal':_h1_terminal}")
    changed=original._PROGRAM_PREFIX+entry+repr(source)+original._PROGRAM_TAIL
    wrapper=_TEMPLATE % dict(here=here,program=changed,public=PUBLIC,types=tuple(sorted(TYPES)))
    if len(wrapper.encode())>100000:
        raise ValueError('terminal_variant_shape_refused')
    return wrapper


_TEMPLATE = '''import json,os,sys
_HERE=%(here)r
_PROGRAM=%(program)r
_PUBLIC=%(public)r
_TYPES=frozenset(%(types)r)
_saved=os.dup(1)
os.set_inheritable(_saved,False)
_handled=_escaping=_exit=_returned=None
_nonzero=False
_actual_rc=0

def _record(event,kind):
    return dict(scope='INTERMEDIATE_ONLY',event=event,module='',function='',line=0,type=kind)

def _public(code):
    path=code.co_filename
    if path=='<fixed-paid-entry>':return path
    for module in _PUBLIC:
        if module!='<fixed-paid-entry>' and path==os.path.join(_HERE,module+'.py'):
            return module
    return None

def _exception(exc,event):
    name=type(exc).__name__
    value=_record(event,name if name in _TYPES else 'UNKNOWN')
    trace=exc.__traceback__
    for unused in range(16):
        if trace is None:break
        code=trace.tb_frame.f_code;module=_public(code)
        if (module in _PUBLIC and code.co_name in _PUBLIC[module]
                and type(trace.tb_lineno)is int and 1<=trace.tb_lineno<=65535):
            value.update(module=module,function=code.co_name,line=trace.tb_lineno)
        trace=trace.tb_next
    return value

def _h1_terminal(exc):
    global _handled
    try:
        _handled=_exception(exc,'HANDLED_TERMINAL_EXCEPTION')
    except BaseException:
        _handled=_record('REPORTER_FAILURE','UNKNOWN')

def _trace(frame,event,arg):
    global _returned
    code=frame.f_code
    if (code.co_filename==os.path.join(_HERE,'remote_sub_exec.py')
            and code.co_name=='_execute'):
        frame.f_trace_lines=False;frame.f_trace_opcodes=False
        if event=='return' and type(arg)is int and arg!=0 and 1<=frame.f_lineno<=65535:
            _returned=_record('TERMINAL_RETURN_NONZERO','NONZERO_RETURN')
            _returned.update(module='remote_sub_exec',function='_execute',line=frame.f_lineno)
        return _trace
    return None

sys.settrace(_trace)
try:
    exec(compile(_PROGRAM,'<fixed-paid-entry>','exec'),
        {'__name__':'__main__','_h1_terminal':_h1_terminal})
except SystemExit as exc:
    _actual_rc=exc.code if type(exc.code)is int and 0<=exc.code<=255 else 78
    _nonzero=_actual_rc!=0
    if _nonzero:_exit=_exception(exc,'ESCAPING_TERMINAL_EXCEPTION')
except BaseException as exc:
    _actual_rc=130 if type(exc)is KeyboardInterrupt else 78
    _nonzero=True
    _escaping=_exception(exc,'ESCAPING_TERMINAL_EXCEPTION')
finally:
    sys.settrace(None)
    value=(_escaping or (_handled if _nonzero else None)
        or (_returned if _nonzero else None) or _exit
        or _record('DIAGNOSTIC_COMPLETED','NO_TERMINAL_REFUSAL'))
    try:
        raw=json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode('ascii')
        if len(raw)<=4096:os.write(_saved,raw+b'\\n')
    except BaseException:
        pass
    finally:os.close(_saved)
raise SystemExit(_actual_rc)
'''


def read_record(raw):
    if type(raw)is not bytes or not 1<len(raw)<=MAX_BYTES+1 or not raw.endswith(b'\n'):
        raise ValueError('terminal_record_refused')
    data=raw[:-1]
    if len(data)>MAX_BYTES or any(b<32 or b>126 for b in data) or b'\\'in data:
        raise ValueError('terminal_record_refused')
    def pairs(items):
        result={}
        for key,value in items:
            if key in result:raise ValueError()
            result[key]=value
        return result
    try:
        value=json.loads(data,object_pairs_hook=pairs,parse_constant=lambda unused:None)
        if (type(value)is not dict or set(value)!=KEYS or value['scope']!=SCOPE
                or value['event']not in EVENTS or value['type']not in TYPES
                or type(value['line'])is not int or not 0<=value['line']<=65535):raise ValueError()
        module=value['module'];function=value['function']
        if not(module==function=='' and value['line']==0):
            if module not in PUBLIC or function not in PUBLIC[module] or value['line']==0:raise ValueError()
        if value['event']=='TERMINAL_RETURN_NONZERO':
            if (module,function,value['type'])!=('remote_sub_exec','_execute','NONZERO_RETURN'):raise ValueError()
        elif value['event']=='DIAGNOSTIC_COMPLETED':
            if module or function or value['line'] or value['type']!='NO_TERMINAL_REFUSAL':raise ValueError()
        elif value['event']=='REPORTER_FAILURE':
            if module or function or value['line'] or value['type']!='UNKNOWN':raise ValueError()
        elif value['type']in ('NONZERO_RETURN','NO_TERMINAL_REFUSAL'):raise ValueError()
        if json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode()!=data:raise ValueError()
    except (ValueError,TypeError,KeyError,UnicodeError,RecursionError):
        raise ValueError('terminal_record_refused') from None
    return value

"""Inert CI diagnostic variant, never an unchanged compiler-execution proof."""
import json

SCHEMA = 'mastermind.inert_compiled_initializer_failure/v2'
FUNCTIONS = frozenset(('UNKNOWN','<module>','_load_qualified_package','run_bootstrap',
    'validate_commitment','refuse','pin','pin_image','no_acl','check','_check',
    '__init__','__enter__','__exit__','_node','_held','_require_startup_entry',
    '_no_site_startup_entries','_initialized_environment','_capture_environment',
    '_bounded_child','bind_effective_context','check_environment','freeze_helper_data',
    'prepare_nested_inputs','sealed_snapshot','require_no_site_policy','path','text','closed'))
KINDS = frozenset(('REFUSAL','ValueError','AssertionError','OSError','PermissionError',
    'InitializerCommitmentRefused','TokenDataRefused','NestedDataRefused'))
STAGES = frozenset(('ENTRY','BOOTSTRAP','HOOK_CAPTURE','CONTEXT','FINAL_OBSERVER'))
ROLES = frozenset(('UNKNOWN','HOME_ANCESTOR','HOME','LANE_ROOT','EXT','HOST_ENV',
    'NESTED_HELPER','CAPTURE_ROOT'))
ACL_KEYS = frozenset(('UNKNOWN','ACCESS','DEFAULT'))


def decode_failure(raw):
    """Reject the whole frame rather than exposing any unrecognized text."""
    try:
        if type(raw) is not bytes or not 0<len(raw)<=4096:return None
        def pairs(items):
            result={}
            for key,value in items:
                if key in result:raise ValueError()
                result[key]=value
            return result
        value=json.loads(raw,object_pairs_hook=pairs)
        if type(value)is not dict or set(value)!={'schema','stage','kind','sites','errno','node_role','acl_key'}:return None
        if value['schema']!=SCHEMA or value['stage'] not in STAGES or value['kind'] not in KINDS:return None
        if value['node_role'] not in ROLES or value['acl_key'] not in ACL_KEYS:return None
        if value['errno'] is not None and (type(value['errno'])is not int or not 0<=value['errno']<=4096):return None
        if type(value['sites'])is not list or len(value['sites'])>6:return None
        for site in value['sites']:
            if type(site)is not dict or set(site)!={'function','line'}:return None
            if site['function'] not in FUNCTIONS or type(site['line'])is not int or not 1<=site['line']<=100000:return None
        return value
    except (ValueError,TypeError,UnicodeError,RecursionError):return None


def instrument_entry(source,*,preamble):
    """Only the test catch/reporter changes; initializer/probe bytes stay fixed.

    This is deliberately a different diagnostic program. The original compiler
    command is measured against its original cap before this local-only variant.
    No hook is retried after a failure to obtain this diagnostic.
    """
    catch='\nexcept Exception:sys.exit(78)\n'
    if type(source)is not str or not source.startswith(preamble) or source.count(catch)!=1:
        raise ValueError('inert_compiled_diagnostic_shape_refused')
    prefix=('import sys as _fd_sys,json as _fd_json\n'
        '_fd_functions='+repr(tuple(sorted(FUNCTIONS)))+'\n'
        '_fd_kinds='+repr(tuple(sorted(KINDS)))+'\n'+r'''
def _fixture_private_role(bootstrap,pin,acl):
    role=key='UNKNOWN'
    if not bootstrap or not pin or not acl:return role,key
    if type(pin.get('fd'))is not int or pin['fd']!=acl.get('fd'):return role,key
    key={'system.posix_acl_access':'ACCESS','system.posix_acl_default':'DEFAULT'}.get(acl.get('key'),'UNKNOWN')
    commitment=bootstrap.get('commitment');request=bootstrap.get('request')
    if type(commitment)is not dict or type(request)is not dict:return role,key
    home=commitment.get('account',{}).get('home');lane=commitment.get('lane_root')
    hook=commitment.get('host_env',{}).get('path');helper=commitment.get('nested_helper',{}).get('path')
    capture=request.get('capture_root')
    if any(type(v)is not str or not v.startswith('/')or len(v)>4096 for v in (home,lane,hook,helper,capture)):return role,key
    if pin.get('name') not in (hook,helper,capture):return role,key
    parts=pin.get('parts');index=pin.get('index')
    if (type(parts)is not list or not 0<len(parts)<=128 or type(index)is not int
            or not 0<=index<len(parts) or any(type(v)is not str or not 0<len(v)<=255 for v in parts)):return role,key
    if '/'+('/'.join(parts))!=pin['name']:return role,key
    node='/'+('/'.join(parts[:index+1]))
    fixed={home:'HOME',lane:'LANE_ROOT',hook.rsplit('/',1)[0]:'EXT',
        hook:'HOST_ENV',helper:'NESTED_HELPER',capture:'CAPTURE_ROOT'}
    if node in fixed:role=fixed[node]
    elif home.startswith(node+'/'):role='HOME_ANCESTOR'
    return role,key
def _fixture_compiled_failure(error):
    try:
        sites=[];names=[];trace=error.__traceback__;bootstrap=pin=acl=None
        while trace is not None:
            name=trace.tb_frame.f_code.co_name
            names.append(name)
            sites.append(dict(function=name if name in _fd_functions else 'UNKNOWN',line=trace.tb_lineno))
            if trace.tb_frame.f_globals.get('__file__')=='<qualified-paid_initializer.py>':
                if name=='run_bootstrap':bootstrap=trace.tb_frame.f_locals
                elif name=='pin':pin=trace.tb_frame.f_locals
                elif name=='no_acl':acl=trace.tb_frame.f_locals
            trace=trace.tb_next
        stage=('HOOK_CAPTURE' if '_capture_environment' in names else
            'CONTEXT' if '_initialized_environment' in names else
            'FINAL_OBSERVER' if '_bounded_child' in names else
            'BOOTSTRAP' if 'run_bootstrap' in names else 'ENTRY')
        kind=type(error).__name__
        if kind not in _fd_kinds:kind='REFUSAL'
        number=getattr(error,'errno',None)
        if type(number)is not int or not 0<=number<=4096:number=None
        sites=[s for s in sites[-6:] if type(s['line'])is int and 1<=s['line']<=100000]
        role,key=_fixture_private_role(bootstrap,pin,acl)
        _fd_sys.stderr.write(_fd_json.dumps(dict(schema='mastermind.inert_compiled_initializer_failure/v2',stage=stage,kind=kind,sites=sites,errno=number,node_role=role,acl_key=key),sort_keys=True,separators=(',',':'))+'\n')
    except Exception:pass
def _fixture_compiled_hook(kind,error,trace):
    if isinstance(error,Exception):_fixture_compiled_failure(error)
    # Rendering is suppressed for interrupts too; CPython still propagates its
    # original interrupt/exit behavior after this hook returns.
_fd_sys.excepthook=_fixture_compiled_hook
''')
    body=source[len(preamble):].replace(catch,
        '\nexcept Exception as _fixture_error:\n    _fixture_compiled_failure(_fixture_error)\n    sys.exit(78)\n')
    return preamble+prefix+body


def failure_notice(request,raw):
    """Best effort only; a malformed/private frame never reaches Actions."""
    try:
        value=decode_failure(raw)
        if value is None:return
        reporter=request.config.pluginmanager.getplugin('terminalreporter')
        if reporter is not None:
            with request.getfixturevalue('capsys').disabled():
                reporter.write_line('\n::error file=tests/test_paid_initializer.py,title=H1 compiled diagnostic variant::'
                    +json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True))
    except Exception:pass


def require_execution_success(execution,request):
    if execution.returncode:
        failure_notice(request,execution.stderr)
        # A plain explicit raise prevents pytest's comparison explanation from
        # rendering CompletedProcess.args/stdout/stderr.
        raise AssertionError('compiled diagnostic variant refused') from None

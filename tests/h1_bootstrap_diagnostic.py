"""Test-only finite pre-model bootstrap diagnostic builder and record parser.

``build_probe(program, here)`` wraps an ORIGINAL, unmodified compiled
``paid_provider_entry._bootstrap_source`` program in a test-only diagnostic
program. Shape validation is not source authentication or a Python sandbox;
the caller supplies its original fixed compiler output over held source.
The wrapper arms ``sys.settrace`` before ``exec``-ing the original
program unchanged, intercepts the exact public
``<here>/paid_provider_entry.py::_run_executor`` frame, and - strictly before
the original function body can run - performs three finite DATA/custody/
compiler checks in fixed order:

1. ``REQUEST``: the actual ``context.request(key, model, packet, env, 1,
   '0'*64)`` correlation against the retained descriptor, capsule and lease
   DATA.
2. ``CAPTURE_OWNER``: the actual held ``paid_model_owner.canonical_state_ext
   (here, env)`` custody observation.
3. ``MODEL_COMMAND``: the original ``executor._canonical_model_command(...,
   context=context, timeout=1)`` local compiler selection.

No ``executor.main``, no LaneLease, no capture creation and no model
execution happen in the diagnostic. A private ``BaseException`` stop unwinds
the real import/owner contexts instead of returning control into the
original body. The wrapper then emits exactly one compact JSON record line
with the fixed schema keys ``outcome phase module function line exception``
(<=4096 bytes stdout, zero stderr on handled failures).

The diagnostic is never positive paid proof; the original paid command is
executed separately by the parent, unchanged. ``parse_record`` and
``read_record`` strictly parse emitted records and refuse malformed,
duplicate-key, extra, private-value, control-character, canary or oversized
payloads with the fixed ``ValueError('invalid_diagnostic_record')``.
"""

import ast
import json
import os

SCHEMA = 'mastermind.h1_bootstrap_diagnostic/v1'

VIRTUAL_MODULE = '<fixed-paid-entry>'
OUTCOMES = ('READY', 'REFUSED')
PHASES = ('BOOTSTRAP', 'REQUEST', 'CAPTURE_OWNER', 'MODEL_COMMAND', 'READY',
          'CLEANUP')

# Fixed public allowlists; never dynamic AST/source-derived names.
MODULES = frozenset((
    'artifact_delivery', 'lane_runtime', 'linux_process_identity',
    'paid_glm_model_client', 'paid_model_owner', 'paid_provider_entry',
    'paid_yaml_runtime', 'remote_sub_exec'))
FUNCTIONS = frozenset((
    '_bootstrap_main', '_canonical_model_command', '_run_executor',
    '_support_imports', '__exit__', 'canonical_state_ext', 'check', 'main',
    'private_input', 'refuse', 'request', 'validate_request'))
EXCEPTIONS = frozenset((
    'AttributeError', 'IndexError', 'KeyError', 'KeyboardInterrupt',
    'MemoryError', 'OSError', 'OverflowError', 'ProviderEntryRefused',
    'RecursionError', 'RuntimeError', 'SystemExit', 'TypeError',
    'UnicodeError', 'ValueError'))

RESULT_KEYS = ('outcome', 'phase', 'module', 'function', 'line', 'exception')

MAX_RECORD_BYTES = 4096
MAX_LINE = 65535
MAX_FRAMES = 16

INVALID_RECORD = 'invalid_diagnostic_record'
PROBE_REFUSED = 'diagnostic_probe_refused'

_MODULE_VALUES = MODULES | frozenset((VIRTUAL_MODULE, ''))
_FUNCTION_VALUES = FUNCTIONS | frozenset(('',))
_EXCEPTION_VALUES = EXCEPTIONS | frozenset(('UNKNOWN', ''))

# Byte-exact shape of an ORIGINAL compiled ``_bootstrap_source`` program.
_PROGRAM_PREFIX = (
    "import sys\n"
    "if sys.version_info[:2]!=(3,12) or not(sys.flags.isolated and sys.flags.no_site "
    "and sys.dont_write_bytecode):raise SystemExit(78)\n"
    "for _n in ('site','sitecustomize','usercustomize'):\n"
    " if _n in sys.modules:raise SystemExit(78)\n"
    " sys.modules[_n]=None\n")
_PROGRAM_ENTRY = "_entry={'__name__':'_fixed_paid_entry'}\nexec(compile("
_PROGRAM_TAIL = (",'<fixed-paid-entry>','exec'),_entry)\n"
                 "raise SystemExit(_entry['_bootstrap_main'](sys.argv[1:]))\n")
_MAX_WRAPPER_BYTES = 100000


def build_probe(program, here):
    """Return the diagnostic wrapper source around the ORIGINAL program.

    ``program`` must be the byte-exact compiled ``_bootstrap_source`` output;
    ``here`` must be the original held public support directory, used for
    exact filename comparisons only. Both are embedded verbatim and never
    output by the wrapper. Anything else is refused, never wrapped.
    """
    if type(program) is not str or type(here) is not str:
        raise ValueError(PROBE_REFUSED)
    if (not here or '\0' in here or not os.path.isabs(here)
            or '..' in here.split(os.sep)):
        raise ValueError(PROBE_REFUSED)
    if not program.startswith(_PROGRAM_PREFIX) or not program.endswith(_PROGRAM_TAIL):
        raise ValueError(PROBE_REFUSED)
    rest = program[len(_PROGRAM_PREFIX):]
    if not rest.startswith(_PROGRAM_ENTRY):
        raise ValueError(PROBE_REFUSED)
    chunk = rest[len(_PROGRAM_ENTRY):len(rest) - len(_PROGRAM_TAIL)]
    try:
        source = ast.literal_eval(chunk)
    except (ValueError, TypeError, SyntaxError, MemoryError, RecursionError):
        raise ValueError(PROBE_REFUSED) from None
    if type(source) is not str or not source or repr(source) != chunk:
        raise ValueError(PROBE_REFUSED)
    wrapper = _WRAPPER_TEMPLATE % {
        'here': here,
        'program': program,
        'modules': tuple(sorted(MODULES)),
        'functions': tuple(sorted(FUNCTIONS)),
        'exceptions': tuple(sorted(EXCEPTIONS)),
        'phases': PHASES,
    }
    if len(wrapper.encode('utf-8')) > _MAX_WRAPPER_BYTES:
        raise ValueError(PROBE_REFUSED)
    return wrapper


_WRAPPER_TEMPLATE = '''import json, os, sys

# Test-only finite bootstrap diagnostic wrapper. Reads stdlib only, preserves
# sys.argv and the no-site flags, emits one fixed-schema JSON record line.
HERE = %(here)r
PROGRAM = %(program)r
_ENTRY_FILE = os.path.join(HERE, 'paid_provider_entry.py')
_MODULES = frozenset(%(modules)r)
_FILES = frozenset(name + '.py' for name in _MODULES)
_FUNCTIONS = frozenset(%(functions)r)
_EXCEPTIONS = frozenset(%(exceptions)r)
_PHASES = %(phases)r
_MAX_RECORD = 4096
_MAX_LINE = 65535


class _ProbeStop(BaseException):
    """Private unwind stop; never caught by the original contexts."""
    pass


_state = {'failed': False, 'intercepted': False, 'checks_complete': False}
_stop = _ProbeStop()
_bootstrap_candidate = None
_record = {'outcome': 'REFUSED', 'phase': 'BOOTSTRAP', 'module': '',
           'function': '', 'line': 0, 'exception': 'UNKNOWN'}


def _approved(code):
    name = code.co_filename
    if name == '<fixed-paid-entry>':
        return '<fixed-paid-entry>'
    base = os.path.basename(name)
    if base in _FILES and name == os.path.join(HERE, base):
        return base[:-3]
    return None


def _facts(tb):
    node = tb
    count = 0
    found = None
    while node is not None and count < 16:
        code = node.tb_frame.f_code
        module = _approved(code)
        if module is not None:
            function = code.co_name
            line = node.tb_lineno
            if (function in _FUNCTIONS and type(line) is int
                    and 0 <= line <= _MAX_LINE):
                found = (module, function, line)
        count += 1
        node = node.tb_next
    return found


def _apply(found):
    if found is not None:
        _record['module'], _record['function'], _record['line'] = found


def _name_of(exc):
    name = type(exc).__name__
    return name if name in _EXCEPTIONS else 'UNKNOWN'


def _record_exception(exc, phase):
    _record['outcome'] = 'REFUSED'
    _record['phase'] = phase
    if exc.__traceback__ is not None:
        _apply(_facts(exc.__traceback__))
    _record['exception'] = _name_of(exc)
    _state['failed'] = True


def _intercept(frame):
    _state['intercepted'] = True
    code = frame.f_code
    first = code.co_firstlineno
    _record['module'] = 'paid_provider_entry'
    _record['function'] = '_run_executor'
    _record['line'] = first if type(first) is int and 0 <= first <= _MAX_LINE else 0
    local = frame.f_locals
    executor = local.get('executor')
    context = local.get('context')
    key = local.get('key')
    model = local.get('model')
    lanes = local.get('lanes')
    accepted = (code.co_argcount == 5
                and code.co_varnames[:5]
                == ('executor', 'context', 'key', 'model', 'lanes')
                and code.co_flags & 0x0C == 0
                and type(key) is str and type(model) is str
                and type(lanes).__module__ == 'pathlib'
                and type(lanes).__name__ in ('Path', 'PosixPath', 'WindowsPath')
                and type(executor).__name__ == 'module'
                and getattr(executor, '__name__', '') == 'remote_sub_exec'
                and getattr(executor, '__file__', '')
                == os.path.join(HERE, 'remote_sub_exec.py')
                and type(context).__name__ == '_ExecutorContext'
                and type(context).__module__ == 'paid_provider_entry')
    if not accepted:
        _record['exception'] = 'UNKNOWN'
        _state['failed'] = True
        raise _stop
    try:
        packet = lanes / 'tmp' / (key + '.txt')
        request = context.request(key, model, packet, os.environ, 1, '0' * 64)
        if type(request) is not dict:
            raise TypeError('request')
    except BaseException as exc:
        _record_exception(exc, 'REQUEST')
        raise _stop
    _record['phase'] = 'REQUEST'
    try:
        import paid_model_owner as owner
        if getattr(owner, '__file__', '') != os.path.join(HERE,
                                                          'paid_model_owner.py'):
            raise TypeError('owner')
        owner.canonical_state_ext(HERE, os.environ)
    except BaseException as exc:
        _record_exception(exc, 'CAPTURE_OWNER')
        raise _stop
    _record['phase'] = 'CAPTURE_OWNER'
    try:
        if os.environ.get('FABRIC_CANONICAL_PAID_MODE') != 'sealed-model-only-v1':
            raise ValueError('mode')
        selected = executor._canonical_model_command(HERE, packet, key, 'glm', model,
                                          os.environ, context=context, timeout=1)
        if type(selected) is not tuple or len(selected) != 2:
            raise TypeError('compiler')
        argv, selected_request = selected
        if (type(argv) is not list or len(argv) != 10
                or any(type(item) is not str or not item or chr(0) in item for item in argv)
                or type(selected_request) is not dict
                or selected_request.get('run_id') != key
                or selected_request.get('model') != model
                or argv[0] != selected_request.get('python_path')
                or argv[1:5] != ['-I', '-S', '-B', '-c']
                or argv[6:8] != ['model', HERE]
                or sum(len(item.encode('utf-8')) + 1 for item in argv) > 100000):
            raise TypeError('compiler')
    except BaseException as exc:
        _record_exception(exc, 'MODEL_COMMAND')
        raise _stop
    _record['phase'] = 'MODEL_COMMAND'
    _state['checks_complete'] = True
    raise _stop


def _probe(frame, event, arg):
    global _bootstrap_candidate
    code = frame.f_code
    if event == 'call' and code.co_name == '_run_executor':
        sys.settrace(None)
        if code.co_filename != _ENTRY_FILE:
            _state['failed'] = True
            raise _stop
        _intercept(frame)
    approved = _approved(code)
    if approved is not None and code.co_name in _FUNCTIONS:
        # Retain only the first allowlisted public exception fact, never
        # text, private locals or arbitrary names. The actual bootstrap
        # swallows Exception; its later SystemExit must not erase this fact.
        if event == 'exception' and _bootstrap_candidate is None:
            line = frame.f_lineno
            if type(line) is int and 1 <= line <= _MAX_LINE:
                _bootstrap_candidate = (approved, code.co_name, line, _name_of(arg[1]))
        return _probe
    return None


_stopped = False
_unwound = None
sys.settrace(_probe)
try:
    exec(compile(PROGRAM, '<fixed-paid-entry>', 'exec'),
         {'__name__': '__main__'})
except _ProbeStop as exc:
    _stopped = exc is _stop
    if not _stopped:
        _unwound = exc
except BaseException as exc:
    _unwound = exc
finally:
    sys.settrace(None)

if _unwound is not None:
    node = _unwound
    guard = 0
    chained = False
    while node is not None and guard < 16:
        if node is _stop:
            chained = True
            break
        node = node.__context__
        guard += 1
    if chained or _state['intercepted']:
        _record['outcome'] = 'REFUSED'
        _record['phase'] = 'CLEANUP'
        if _unwound.__traceback__ is not None:
            _apply(_facts(_unwound.__traceback__))
        _record['exception'] = _name_of(_unwound)
    elif not _state['failed']:
        _record_exception(_unwound, 'BOOTSTRAP')
        if _bootstrap_candidate is not None:
            _record['module'], _record['function'], _record['line'], _record['exception'] = _bootstrap_candidate
elif (_stopped and _state['intercepted'] and _state['checks_complete']
        and not _state['failed']):
    _record['outcome'] = 'READY'
    _record['phase'] = 'READY'
    _record['exception'] = ''
elif _state['intercepted'] and not _stopped:
    _record['phase'] = 'CLEANUP'
    _record['exception'] = 'UNKNOWN'

sys.settrace(None)
if _record['outcome'] not in ('READY', 'REFUSED'):
    _record['outcome'] = 'REFUSED'
if _record['phase'] not in _PHASES:
    _record['phase'] = 'BOOTSTRAP'
if _record['module'] not in _MODULES and _record['module'] != '<fixed-paid-entry>':
    _record['module'] = ''
if _record['function'] not in _FUNCTIONS:
    _record['function'] = ''
if type(_record['line']) is not int or not 0 <= _record['line'] <= _MAX_LINE:
    _record['line'] = 0
if _record['exception'] not in _EXCEPTIONS and _record['exception'] not in ('UNKNOWN', ''):
    _record['exception'] = 'UNKNOWN'
data = json.dumps(_record, sort_keys=True, separators=(',', ':'),
                  ensure_ascii=True).encode('ascii')
if len(data) <= _MAX_RECORD:
    try:
        sys.stdout.buffer.write(data + b'\\n')
        sys.stdout.buffer.flush()
    except (OSError, ValueError):
        pass
raise SystemExit(0)
'''


def _pairs(items):
    seen = {}
    for key, value in items:
        if type(key) is not str or key in seen:
            raise ValueError(INVALID_RECORD)
        seen[key] = value
    return seen


def _constant(token):
    raise ValueError(INVALID_RECORD)


def _decode_line(raw):
    if type(raw) not in (bytes, bytearray, str) or not 0 < len(raw) <= MAX_RECORD_BYTES + 1:
        raise ValueError(INVALID_RECORD)
    if type(raw) in (bytes, bytearray):
        try:
            raw = bytes(raw).decode('ascii')
        except (UnicodeDecodeError, ValueError):
            raise ValueError(INVALID_RECORD) from None
    if type(raw) is not str:
        raise ValueError(INVALID_RECORD)
    return raw


def parse_record(raw):
    """Strictly parse one fixed-schema diagnostic record line.

    Accepts only the canonical compact ASCII JSON object with exactly the
    fixed keys, fixed enum values and a bounded uint line. Any malformed,
    duplicate-key, extra, private-value, control-character, canary, escaped,
    non-canonical or oversized payload raises the fixed ValueError with no
    other content.
    """
    text = _decode_line(raw)
    if text.endswith('\n'):
        text = text[:-1]
    if not text or len(text) > MAX_RECORD_BYTES:
        raise ValueError(INVALID_RECORD)
    for char in text:
        if ord(char) < 0x20 or ord(char) == 0x7F:
            raise ValueError(INVALID_RECORD)
    if '\\' in text or 'FABRIC_' in text:
        raise ValueError(INVALID_RECORD)
    try:
        record = json.loads(text, object_pairs_hook=_pairs,
                            parse_constant=_constant)
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise ValueError(INVALID_RECORD) from None
    if type(record) is not dict or set(record) != set(RESULT_KEYS):
        raise ValueError(INVALID_RECORD)
    if (type(record['outcome']) is not str or record['outcome'] not in OUTCOMES
            or type(record['phase']) is not str or record['phase'] not in PHASES
            or type(record['module']) is not str
            or record['module'] not in _MODULE_VALUES
            or type(record['function']) is not str
            or record['function'] not in _FUNCTION_VALUES
            or type(record['exception']) is not str
            or record['exception'] not in _EXCEPTION_VALUES
            or type(record['line']) is not int
            or not 0 <= record['line'] <= MAX_LINE):
        raise ValueError(INVALID_RECORD)
    if record['outcome'] == 'READY':
        if (record['phase'] != 'READY' or record['exception'] != ''
                or record['module'] != 'paid_provider_entry'
                or record['function'] != '_run_executor' or record['line'] < 1):
            raise ValueError(INVALID_RECORD)
    elif record['phase'] == 'READY' or record['exception'] == '':
        raise ValueError(INVALID_RECORD)
    canonical = json.dumps(record, sort_keys=True, separators=(',', ':'),
                           ensure_ascii=True)
    if canonical != text:
        raise ValueError(INVALID_RECORD)
    return {key: record[key] for key in RESULT_KEYS}


def read_record(data):
    """Parse the single complete record line from a probe stdout payload."""
    text = _decode_line(data)
    if not text.endswith('\n') or '\r' in text or '\0' in text:
        raise ValueError(INVALID_RECORD)
    body = text[:-1]
    if '\n' in body:
        raise ValueError(INVALID_RECORD)
    return parse_record(body)

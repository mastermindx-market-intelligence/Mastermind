"""Focused tests for the test-only finite bootstrap diagnostic helper.

Covers ``build_probe`` acceptance/refusal, the strict fixed-record parser,
and fresh ``python3 -I -S -B`` subprocess runs of the emitted wrapper against
synthetic exact public frames: READY without executing the original body,
failure at each finite phase, cleanup override, and unknown/private/text/
canary/control-path redaction. The synthetic frames live in a fresh
temporary support directory; no real host/account/HOME/lease/admission/
capture/model/provider/service/credential effects are used and the real
program payload is never copied here.
"""

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location(
    'h1_bootstrap_diagnostic_under_test', os.path.join(_HERE, 'h1_bootstrap_diagnostic.py'))
diag = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(diag)


def _python312():
    if sys.version_info[:2] == (3, 12):
        return sys.executable
    for candidate in ('/usr/bin/python3.12', '/usr/local/bin/python3.12'):
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    raise RuntimeError('python3.12 interpreter required for probe subprocesses')


def _line(source, marker):
    """1-based line of the first ``marker`` occurrence in a source string."""
    index = source.index(marker)
    return source.count('\n', 0, index) + 1


_PREAMBLE = (
    "import sys\n"
    "if sys.version_info[:2]!=(3,12) or not(sys.flags.isolated and sys.flags.no_site "
    "and sys.dont_write_bytecode):raise SystemExit(78)\n"
    "for _n in ('site','sitecustomize','usercustomize'):\n"
    " if _n in sys.modules:raise SystemExit(78)\n"
    " sys.modules[_n]=None\n")


def _bootstrap_like(source):
    """Replica of the public compiled ``_bootstrap_source`` program shape."""
    return (_PREAMBLE
            + "_entry={'__name__':'_fixed_paid_entry'}\nexec(compile("
            + repr(source) + ",'<fixed-paid-entry>','exec'),_entry)\n"
            + "raise SystemExit(_entry['_bootstrap_main'](sys.argv[1:]))\n")


FAKE_ENTRY = '''
import sys


class ProviderEntryRefused(ValueError):
    def __init__(self):
        super().__init__('canonical_paid_provider_entry_refused')


def refuse():
    raise ProviderEntryRefused() from None


class _PrivateStop(BaseException):
    pass


class _ExecutorContext:
    def __init__(self, scenario):
        self.scenario = scenario

    def request(self, key, model, packet, env, timeout, nonce):
        if self.scenario == 'request':
            refuse()
        if self.scenario == 'interrupt':
            raise KeyboardInterrupt()
        if self.scenario == 'unknown':
            raise _PrivateStop('secret-private-stop')
        if self.scenario == 'secret':
            raise ValueError('secret-value-error-message')
        if self.scenario == 'badshape':
            return ['not-a-dict']
        return {'run_id': key, 'model': model}


class _Gate:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        refused = ProviderEntryRefused()
        raise refused from None


def _run_executor(executor, context, key, model, lanes):
    sys.stdout.write('BODY-EXECUTED-CANARY\\n')
    sys.stdout.flush()
    return 78
'''

FAKE_OWNER = '''
SCENARIO = ''


def canonical_state_ext(here, env):
    if SCENARIO == 'capture':
        raise KeyError('secret-capture-message')
    return here
'''

FAKE_EXEC = '''
SCENARIO = ''


def _canonical_model_command(here, packet, key, mode, model, env,
                             context=None, timeout=1):
    if SCENARIO == 'command':
        raise ValueError('CANONICAL_PAID_MODE_REFUSED')
    if SCENARIO == 'none-command':return None
    if SCENARIO == 'list-command':return [[], {}]
    request={'run_id':key,'model':model,'python_path':'/usr/bin/python3.12'}
    argv=[request['python_path'],'-I','-S','-B','-c','public-model-bootstrap',
          'model',here,'encoded-public-support','encoded-fixture-request']
    if SCENARIO == 'bad-command':argv[1]='-S'
    return argv,request
'''

FAKE_SOURCE = (
    "import os\nimport pathlib\nimport sys\nimport types\n\n"
    "SOURCES = (('paid_provider_entry', " + repr(FAKE_ENTRY)
    + "), ('paid_model_owner', " + repr(FAKE_OWNER)
    + "), ('remote_sub_exec', " + repr(FAKE_EXEC) + "))\n"
    "\n"
    "def _bootstrap_main(args):\n"
    "    here = args[1]\n"
    "    scenario = args[2]\n"
    "    modules = {}\n"
    "    for name, source in SOURCES:\n"
    "        module = types.ModuleType(name)\n"
    "        owner_file = 'paid_model_owner.py'\n"
    "        if scenario == 'custody' and name == 'paid_model_owner':\n"
    "            owner_file = 'tampered_owner.py'\n"
    "        if name == 'paid_model_owner':\n"
    "            module.__file__ = os.path.join(here, owner_file)\n"
    "        else:\n"
    "            module.__file__ = os.path.join(here, name + '.py')\n"
    "        exec(compile(source, module.__file__, 'exec'), module.__dict__)\n"
    "        modules[name] = module\n"
    "        sys.modules[name] = module\n"
    "    entry = modules['paid_provider_entry']\n"
    "    owner = modules['paid_model_owner']\n"
    "    executor = modules['remote_sub_exec']\n"
    "    owner.SCENARIO = scenario\n"
    "    executor.SCENARIO = scenario\n"
    "    context = entry._ExecutorContext(scenario)\n"
    "    lanes = pathlib.Path(here).parent.parent.parent\n"
    "    if scenario == 'bootstrap':\n"
    "        raise SystemExit(78)\n"
    "    if scenario == 'cleanup':\n"
    "        with entry._Gate():\n"
    "            return entry._run_executor(executor, context,\n"
    "                                       'probe-run-1', 'glm-5.3', lanes)\n"
    "    if scenario == 'mismatch':\n"
    "        return entry._run_executor(executor, object(),\n"
    "                                   'probe-run-1', 'glm-5.3', lanes)\n"
    "    if scenario == 'normal':\n"
    "        return 0\n"
    "    return entry._run_executor(executor, context, 'probe-run-1',\n"
    "                               'glm-5.3', lanes)\n")

L_ENTRY = _line(FAKE_ENTRY, 'def _run_executor')
L_REFUSE = _line(FAKE_ENTRY, 'raise ProviderEntryRefused() from None')
L_INTERRUPT = _line(FAKE_ENTRY, 'raise KeyboardInterrupt()')
L_PRIVATE = _line(FAKE_ENTRY, 'raise _PrivateStop(')
L_SECRET = _line(FAKE_ENTRY, "raise ValueError('secret-value-error-message')")
L_EXIT = _line(FAKE_ENTRY, 'raise refused from None')
L_CAPTURE = _line(FAKE_OWNER, 'raise KeyError(')
L_COMMAND = _line(FAKE_EXEC, 'raise ValueError(')
L_BOOTSTRAP_STOP = _line(FAKE_SOURCE, 'raise SystemExit(78)')

EXPECTED = {
    'ready': ('READY', 'READY', 'paid_provider_entry', '_run_executor',
              L_ENTRY, ''),
    'request': ('REFUSED', 'REQUEST', 'paid_provider_entry', 'refuse',
                L_REFUSE, 'ProviderEntryRefused'),
    'interrupt': ('REFUSED', 'REQUEST', 'paid_provider_entry', 'request',
                  L_INTERRUPT, 'KeyboardInterrupt'),
    'unknown': ('REFUSED', 'REQUEST', 'paid_provider_entry', 'request',
                L_PRIVATE, 'UNKNOWN'),
    'secret': ('REFUSED', 'REQUEST', 'paid_provider_entry', 'request',
               L_SECRET, 'ValueError'),
    'badshape': ('REFUSED', 'REQUEST', 'paid_provider_entry', '_run_executor',
                 L_ENTRY, 'TypeError'),
    'capture': ('REFUSED', 'CAPTURE_OWNER', 'paid_model_owner',
                'canonical_state_ext', L_CAPTURE, 'KeyError'),
    'custody': ('REFUSED', 'CAPTURE_OWNER', 'paid_provider_entry',
                '_run_executor', L_ENTRY, 'TypeError'),
    'command': ('REFUSED', 'MODEL_COMMAND', 'remote_sub_exec',
                '_canonical_model_command', L_COMMAND, 'ValueError'),
    'cleanup': ('REFUSED', 'CLEANUP', 'paid_provider_entry', '__exit__',
                L_EXIT, 'ProviderEntryRefused'),
    'mismatch': ('REFUSED', 'BOOTSTRAP', 'paid_provider_entry',
                 '_run_executor', L_ENTRY, 'UNKNOWN'),
    'bootstrap': ('REFUSED', 'BOOTSTRAP', diag.VIRTUAL_MODULE,
                  '_bootstrap_main', L_BOOTSTRAP_STOP, 'SystemExit'),
    'normal': ('REFUSED', 'BOOTSTRAP', '', '', 0, 'SystemExit'),
}

SECRET_MARKERS = (
    'secret-private-stop', 'secret-value-error-message',
    'secret-capture-message', 'CANONICAL_PAID_MODE_REFUSED',
    'canonical_paid_provider_entry_refused', 'BODY-EXECUTED-CANARY',
    'FABRIC_', 'probe-run-1')


def _canonical(record):
    return json.dumps(record, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=True)


VALID_RECORD = {'outcome': 'READY', 'phase': 'READY',
                'module': 'paid_provider_entry',
                'function': '_run_executor', 'line': 120, 'exception': ''}


class BuildProbeTests(unittest.TestCase):
    def setUp(self):
        self.here = os.path.join(tempfile.gettempdir(), 'h1-diag-build-here')
        self.program = _bootstrap_like(FAKE_SOURCE)

    def test_builds_wrapper_around_unmodified_program(self):
        first = diag.build_probe(self.program, self.here)
        second = diag.build_probe(self.program, self.here)
        self.assertEqual(first, second)
        self.assertIn(repr(self.program), first)
        self.assertIn(repr(self.here), first)
        self.assertIn('sys.settrace', first)
        self.assertIn("exec(compile(PROGRAM, '<fixed-paid-entry>', 'exec')",
                      first)
        self.assertLessEqual(len(first.encode('utf-8')), 100000)
        compile(first, '<probe-wrapper>', 'exec')

    def test_wrapper_prefix_is_stdlib_only_without_path_fallback(self):
        wrapper = diag.build_probe(self.program, self.here)
        prefix = wrapper.split('\n', 1)[0]
        self.assertEqual(prefix, 'import json, os, sys')
        self.assertNotIn('import site', wrapper)
        self.assertNotIn('sys.path', wrapper)

    def test_refuses_non_program_strings(self):
        damaged_tail = self.program.replace('_entry[\'_bootstrap_main\']',
                                            '_entry[\'_evil_main\']')
        damaged_prefix = self.program.replace(
            'sys.version_info[:2]!=(3,12)', 'sys.version_info[:2]!=(3,13)')
        damaged_literal = (_PREAMBLE
                           + "_entry={'__name__':'_fixed_paid_entry'}\n"
                           + "exec(compile(not-a-literal,"
                           + "'<fixed-paid-entry>','exec'),_entry)\n"
                           + "raise SystemExit("
                           + "_entry['_bootstrap_main'](sys.argv[1:]))\n")
        cases = ['', 'print(1)', _PREAMBLE, _PREAMBLE + 'x=1\n',
                 damaged_tail, damaged_prefix, damaged_literal,
                 None, 123, b'bytes', ['list']]
        for program in cases:
            with self.subTest(program=repr(program)[:40]):
                with self.assertRaises(ValueError) as ctx:
                    diag.build_probe(program, self.here)
                self.assertEqual(str(ctx.exception), diag.PROBE_REFUSED)

    def test_refuses_unsafe_here(self):
        for here in ('', 'relative/path', './here', '../up', '/tmp/../etc',
                     '/tmp\0hidden', None, 7, b'/tmp/bytes'):
            with self.subTest(here=repr(here)):
                with self.assertRaises(ValueError) as ctx:
                    diag.build_probe(self.program, here)
                self.assertEqual(str(ctx.exception), diag.PROBE_REFUSED)


class ParseRecordTests(unittest.TestCase):
    def test_accepts_canonical_record(self):
        text = _canonical(VALID_RECORD)
        self.assertEqual(diag.parse_record(text), VALID_RECORD)
        self.assertEqual(diag.parse_record(text + '\n'), VALID_RECORD)
        self.assertEqual(diag.parse_record(text.encode('ascii')), VALID_RECORD)
        self.assertEqual(diag.read_record(text.encode('ascii') + b'\n'),
                         VALID_RECORD)
        self.assertEqual(sorted(diag.parse_record(text + '\n')),
                         sorted(diag.RESULT_KEYS))

    def test_refuses_malformed_duplicate_extra_private_and_bounded(self):
        duplicate = ('{"exception":"","function":"_run_executor","line":120,'
                     '"module":"paid_provider_entry","outcome":"READY",'
                     '"outcome":"READY","phase":"READY"}')
        missing = {key: value for key, value in VALID_RECORD.items()
                   if key != 'line'}
        big = '{"x":"' + 'a' * 5000 + '"}'
        nan = ('{"exception":"","function":"","line":0,"module":"",'
               '"outcome":"READY","phase":NaN}')
        cases = [
            '', '\n', 'nonsense', '{', 'null', '[]',
            _canonical(VALID_RECORD)[:-1],
            _canonical(VALID_RECORD) + ' trailing',
            _canonical(VALID_RECORD) + '\n' + _canonical(VALID_RECORD),
            '  ' + _canonical(VALID_RECORD), _canonical(VALID_RECORD) + ' ',
            duplicate, _canonical(dict(VALID_RECORD, private='x')),
            _canonical(missing),
            _canonical(dict(VALID_RECORD, outcome='PASS')),
            _canonical(dict(VALID_RECORD, phase='SETUP')),
            _canonical(dict(VALID_RECORD, module='../evil')),
            _canonical(dict(VALID_RECORD, module='paid_provider_entry.py')),
            _canonical(dict(VALID_RECORD, function='exec')),
            _canonical(dict(VALID_RECORD, exception='MyPrivateError')),
            _canonical(dict(VALID_RECORD, exception='READY')),
            _canonical(dict(VALID_RECORD, line=-1)),
            _canonical(dict(VALID_RECORD, line=65536)),
            _canonical(dict(VALID_RECORD, line='3')),
            _canonical(dict(VALID_RECORD, line=1.0)),
            _canonical(dict(VALID_RECORD, line=True)),
            _canonical(dict(VALID_RECORD, line=None)),
            _canonical(VALID_RECORD) + '\x1b[0m',
            '\x07', _canonical(VALID_RECORD) + '\r',
            _canonical(dict(VALID_RECORD, module='paid_provider_entry\r')),
            _canonical(VALID_RECORD).replace('READY', 'FABRIC_READY', 1),
            _canonical(dict(VALID_RECORD,
                            module='\\u0070aid_provider_entry')),
            big, nan, b'\xff\xfe', None, 123, {'not': 'text'},
        ]
        for text in cases:
            with self.subTest(text=repr(text)[:48]):
                with self.assertRaises(ValueError) as ctx:
                    diag.parse_record(text)
                self.assertEqual(str(ctx.exception),
                                 diag.INVALID_RECORD)

    def test_read_record_line_structure(self):
        valid = _canonical(VALID_RECORD)
        for data in (b'no newline', b'two\nlines\n', b'\xc3\xa4\n',
                     valid.encode('ascii') + b'\nextra\n', b'\r\n'):
            with self.subTest(data=data):
                with self.assertRaises(ValueError) as ctx:
                    diag.read_record(data)
                self.assertEqual(str(ctx.exception), diag.INVALID_RECORD)


class ProbeSubprocessTests(unittest.TestCase):
    maxDiff = None

    @classmethod
    def setUpClass(cls):
        cls.interpreter = _python312()
        cls.here = tempfile.mkdtemp(prefix='h1-diag-here-')
        cls.program = _bootstrap_like(FAKE_SOURCE)
        cls.wrapper = diag.build_probe(cls.program, cls.here)
        cls.runs = {}
        for scenario in sorted(EXPECTED):
            cls.runs[scenario] = subprocess.run(
                [cls.interpreter, '-I', '-S', '-B', '-c', cls.wrapper,
                 'executor', cls.here, scenario],
                capture_output=True, timeout=120,
                env={'PATH': '/usr/bin:/bin',
                     'FABRIC_CANONICAL_PAID_MODE':'sealed-model-only-v1'})

    @classmethod
    def tearDownClass(cls):
        for path in (cls.here,):
            if os.path.isdir(path):
                os.rmdir(path)

    def test_scenarios_reach_fixed_records(self):
        for scenario, expected in sorted(EXPECTED.items()):
            with self.subTest(scenario=scenario):
                done = self.runs[scenario]
                self.assertEqual(done.returncode, 0, "probe subprocess refused")
                self.assertEqual(done.stderr, b'')
                record = diag.read_record(done.stdout)
                self.assertEqual(set(record), set(diag.RESULT_KEYS))
                self.assertEqual(
                    (record['outcome'], record['phase'], record['module'],
                     record['function'], record['line'],
                     record['exception']), expected)

    def test_ready_passes_checks_without_executing_body(self):
        done = self.runs['ready']
        record = diag.read_record(done.stdout)
        self.assertEqual(record['outcome'], 'READY')
        self.assertEqual(record['phase'], 'READY')
        self.assertEqual(record['exception'], '')
        self.assertEqual(record['module'], 'paid_provider_entry')
        self.assertEqual(record['function'], '_run_executor')
        self.assertEqual(record['line'], L_ENTRY)
        self.assertNotIn(b'BODY-EXECUTED-CANARY', done.stdout)
        self.assertEqual(done.stderr, b'')

    def test_stdout_is_single_line_without_paths_or_private_text(self):
        for scenario, done in sorted(self.runs.items()):
            with self.subTest(scenario=scenario):
                self.assertLessEqual(len(done.stdout), diag.MAX_RECORD_BYTES)
                self.assertTrue(done.stdout.endswith(b'\n'))
                self.assertEqual(done.stdout.count(b'\n'), 1)
                self.assertNotIn(b'\r', done.stdout)
                self.assertNotIn(b'\x1b', done.stdout)
                text = done.stdout.decode('ascii')
                self.assertNotIn(self.here, text)
                self.assertNotIn(tempfile.gettempdir(), text)
                self.assertNotIn('\\', text)
                self.assertNotIn('FABRIC_', text)
                for marker in SECRET_MARKERS:
                    self.assertNotIn(marker, text)
                record = diag.parse_record(text)
                self.assertEqual(sorted(record), sorted(diag.RESULT_KEYS))

    def test_original_body_never_executes_in_any_scenario(self):
        for scenario, done in sorted(self.runs.items()):
            with self.subTest(scenario=scenario):
                self.assertNotIn(b'BODY-EXECUTED-CANARY', done.stdout)


class SafetyRegressionTests(unittest.TestCase):
    def run_probe(self, scenario, source=FAKE_SOURCE, *, selected=True):
        with tempfile.TemporaryDirectory(prefix='h1-probe-safety-') as here:
            wrapper=diag.build_probe(_bootstrap_like(source),here)
            env={'PATH':'/usr/bin:/bin'}
            if selected:env['FABRIC_CANONICAL_PAID_MODE']='sealed-model-only-v1'
            result=subprocess.run([_python312(),'-I','-S','-B','-c',wrapper,
                'executor',here,scenario],capture_output=True,env=env,timeout=20)
            self.assertEqual(result.returncode,0,'finite child refused')
            self.assertEqual(result.stderr,b'')
            self.assertNotIn(b'BODY-EXECUTED-CANARY',result.stdout)
            self.assertNotIn(here.encode(),result.stdout)
            self.assertNotIn(b'secret',result.stdout)
            return diag.read_record(result.stdout)

    def test_none_non_tuple_and_wrong_argv_cannot_qualify(self):
        for scenario in ('none-command','list-command','bad-command'):
            with self.subTest(scenario=scenario):
                value=self.run_probe(scenario)
                self.assertEqual((value['outcome'],value['phase'],value['exception']),
                    ('REFUSED','MODEL_COMMAND','TypeError'))

    def test_absent_canonical_mode_cannot_qualify(self):
        value=self.run_probe('ready',selected=False)
        self.assertEqual((value['outcome'],value['phase']),('REFUSED','MODEL_COMMAND'))

    def test_wrong_filename_executor_body_never_executes(self):
        source=FAKE_SOURCE.replace(
            "module.__file__ = os.path.join(here, name + '.py')",
            "module.__file__ = os.path.join(here, 'foreign.py' if name == 'paid_provider_entry' else name + '.py')")
        value=self.run_probe('ready',source)
        self.assertEqual((value['outcome'],value['phase']),('REFUSED','BOOTSTRAP'))
        self.assertEqual((value['module'],value['function'],value['line']),('', '', 0))

    def test_early_wrong_instance_of_private_stop_cannot_qualify(self):
        for expression in ("sys.gettrace().__globals__['_ProbeStop']()",
                           "sys.gettrace().__globals__['_stop']"):
            with self.subTest(expression=expression):
                source=FAKE_SOURCE.replace("    if scenario == 'bootstrap':",
                    "    if scenario == 'early-stop':\n"
                    "        raise "+expression+"\n"
                    "    if scenario == 'bootstrap':")
                value=self.run_probe('early-stop',source)
                self.assertEqual((value['outcome'],value['phase']),('REFUSED','BOOTSTRAP'))

    def test_swallowed_or_replaced_stop_is_cleanup_refusal(self):
        entry=FAKE_ENTRY.replace("        refused = ProviderEntryRefused()",
            "        if _SCENARIO == 'swallow':return True\n"
            "        if _SCENARIO == 'wrong-stop':raise _FOREIGN_STOP()\n"
            "        refused = ProviderEntryRefused()")
        source=FAKE_SOURCE.replace(repr(FAKE_ENTRY),repr(entry))
        source=source.replace("    context = entry._ExecutorContext(scenario)",
            "    entry._SCENARIO=scenario\n"
            "    entry._FOREIGN_STOP=sys.gettrace().__globals__['_ProbeStop']\n"
            "    context = entry._ExecutorContext(scenario)")
        source=source.replace("    if scenario == 'cleanup':",
            "    if scenario in ('cleanup','swallow','wrong-stop'):")
        source=source.replace("    if scenario == 'mismatch':", "        return 0\n    if scenario == 'mismatch':")
        for scenario in ('cleanup','swallow','wrong-stop'):
            with self.subTest(scenario=scenario):
                value=self.run_probe(scenario,source)
                self.assertEqual((value['outcome'],value['phase']),('REFUSED','CLEANUP'))

    def test_swallowed_bootstrap_exception_keeps_public_primary_reason(self):
        source=FAKE_SOURCE.replace("    if scenario == 'bootstrap':",
            "    if scenario == 'swallowed-bootstrap':\n"
            "        try:entry.refuse()\n"
            "        except Exception:return 78\n"
            "    if scenario == 'bootstrap':")
        value=self.run_probe('swallowed-bootstrap',source)
        self.assertEqual((value['outcome'],value['phase'],value['module'],
            value['function'],value['exception']),
            ('REFUSED','BOOTSTRAP','paid_provider_entry','refuse','ProviderEntryRefused'))

    def test_semantically_inconsistent_ready_records_refuse(self):
        invalid=[]
        for phase in diag.PHASES:
            if phase!='READY':invalid.append(dict(VALID_RECORD,phase=phase))
        for exception in ('UNKNOWN','ValueError'):
            invalid.append(dict(VALID_RECORD,exception=exception))
        for module in ('','remote_sub_exec'):
            invalid.append(dict(VALID_RECORD,module=module))
        for function in ('','request'):
            invalid.append(dict(VALID_RECORD,function=function))
        invalid.append(dict(VALID_RECORD,line=0))
        invalid.append(dict(VALID_RECORD,outcome='REFUSED',exception='UNKNOWN'))
        invalid.append(dict(VALID_RECORD,outcome='REFUSED',phase='REQUEST'))
        for value in invalid:
            with self.subTest(value=value):
                with self.assertRaises(ValueError) as caught:diag.read_record(_canonical(value)+'\n')
                self.assertEqual(str(caught.exception),diag.INVALID_RECORD)


if __name__ == '__main__':
    unittest.main()

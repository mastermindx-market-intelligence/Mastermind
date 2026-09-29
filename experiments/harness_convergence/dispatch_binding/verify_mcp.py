"""Offline qualification of the existing MCP bridge's optional admission path."""
from __future__ import annotations

import datetime as dt
import json
import os
import platform
import shutil
import subprocess
import sys
import time
from pathlib import Path
from prepare import ROOT, CACHE, digest, prepare as prepare_core
from prepare_mcp import prepare

EXPECTED_RED = {
    'tool admission does not publish server instructions',
    'tool admission does not authorize resources/list',
    'tool admission does not authorize resources/templates/list',
    'tool admission does not authorize resources/read',
    'empty admitted tool set does not expose other context channels',
    'exposes only admitted tools and returns a real server nonce',
    'passes immutable complete schemas and actual server identity to admission',
    'refuses revoked permission after an asynchronous wrapper',
    'refuses a disconnected connection generation before sending',
    'retires the old generation when re-admission refuses schema drift',
    'retires the old generation before a failing list request',
    'retires the previous generation while refreshed discovery is pending',
    'retained old definition cannot send after a successful replacement sync',
    'refuses unlisted tool without exposure or execution',
    'refuses duplicate selection without exposure or execution',
    'refuses nonfunction guard without exposure or execution',
    'refuses async admission without exposure or execution',
    'requires live connection binding when admission is enabled',
    'requires a literal true from the final execution guard',
    'keeps a completed old-generation call attributable without resending it',
    'threads admission through the actual connection startup owner',
    'rejects a server-identity mismatch before exposing tools',
    'rejects public display names supplied as raw grant identities',
    'captures the selected guard instead of a mutable grant-property lookup',
    'rejects a generation that disconnects while discovery is suspended',
    'checks currentness again after the admission callback',
    'lets the owner reject changed output schemas from real tools/list',
    'allows an explicitly empty selection without inventing a required capability',
    'uses the same admission hook on actual SDK tool-list notifications',
}
NODE = shutil.which('node')
if NODE is None:
    raise SystemExit('Node is required; no executable will be installed')
ENV = {'PATH': str(Path(NODE).parent) + ':/usr/bin:/bin',
       'HOME': str(CACHE / 'home'), 'TMPDIR': str(CACHE / 'tmp'), 'CI': '1'}


def suite(name: str, source: str, expected: set[str], upstream: bool = False, stdio: bool = False,
          profile: bool = False, profile_source: str = 'runtime') -> dict:
    destination = CACHE / f'{name}.json'
    start = time.monotonic()
    result = subprocess.run(
        [NODE, 'node_modules/vitest/vitest.mjs', 'run', '--config', 'vitest.mcp.config.mjs',
         '--reporter=json', f'--outputFile={destination}'], cwd=ROOT,
        env={**ENV, 'MMX_MCP_SOURCE': source, 'MMX_MCP_UPSTREAM': '1' if upstream else '0',
             'MMX_MCP_STDIO': '1' if stdio else '0',
             'MMX_MCP_PROFILE': '1' if profile else '0', 'MMX_PROFILE_SOURCE': profile_source},
        capture_output=True, text=True, timeout=60, check=False,
    )
    output = result.stdout + result.stderr
    (CACHE / f'{name}.log').write_text(output)
    data = json.loads(destination.read_text())
    assertions = [a for s in data['testResults'] for a in s.get('assertionResults', [])]
    count = 19 if profile else 12 if stdio else 121 if upstream else 32
    failed = {a['title'] for a in assertions if a['status'] == 'failed'}
    assert len(assertions) == data['numTotalTests'] == count, f'{name}: missing cases'
    assert all(a['status'] in {'passed', 'failed'} for a in assertions), f'{name}: skipped cases'
    assert data['numPendingTests'] == 0 and not result.stderr, f'{name}: incomplete execution'
    assert failed == expected, f'{name}: unexpected failures {sorted(failed)}'
    assert result.returncode == (1 if expected else 0), f'{name}: unexpected exit'
    assert data['numPassedTests'] == count - len(expected)
    assert data['numFailedTests'] == len(expected)
    for assertion in assertions:
        if assertion['status'] == 'failed':
            messages = assertion.get('failureMessages', [])
            assert messages and all('AssertionError:' in m or 'promise resolved' in m for m in messages), name
    return {'tests': count, 'passed': data['numPassedTests'], 'failed_cases': sorted(failed),
            'exit_code': result.returncode, 'seconds': round(time.monotonic() - start, 3),
            'stderr_empty': True, 'report_sha256': digest(destination.read_bytes()),
            'log_sha256': digest(output.encode()), 'cases': [a['title'] for a in assertions]}


def typecheck() -> dict:
    result = subprocess.run([NODE, 'node_modules/typescript/bin/tsc', '-p', 'tsconfig.mcp.json'],
                            cwd=ROOT, env=ENV, capture_output=True, text=True, timeout=30)
    output = result.stdout + result.stderr
    (CACHE / 'mcp-typecheck.log').write_text(output)
    assert result.returncode == 0 and not output, 'MCP strict typecheck failed'
    return {'exit_code': 0, 'output_sha256': digest(output.encode())}


MUTATIONS = {
    'context': ('connection.ts', 'const toolOnly = admitGeneration !== undefined',
                'const toolOnly = false', {
        'tool admission does not publish server instructions',
        'tool admission does not authorize resources/list',
        'tool admission does not authorize resources/templates/list',
        'tool admission does not authorize resources/read',
        'empty admitted tool set does not expose other context channels',
    }),
    'filter': ('tools.ts', 'if (strict && allow === undefined) continue',
               'if (false && allow === undefined) continue', {
        'exposes only admitted tools and returns a real server nonce',
        'keeps a completed old-generation call attributable without resending it',
        'threads admission through the actual connection startup owner',
        'empty admitted tool set does not expose other context channels',
        'allows an explicitly empty selection without inventing a required capability',
        'uses the same admission hook on actual SDK tool-list notifications',
    }),
    'dispatch': ('tools.ts', 'if (strict && (!active || !isCurrent() || allow?.(execution) !== true',
                 'if (false && (!active || !isCurrent() || allow?.(execution) !== true', {
        'refuses revoked permission after an asynchronous wrapper',
        'refuses a disconnected connection generation before sending',
        'retained old definition cannot send after a successful replacement sync',
        'requires a literal true from the final execution guard',
        'captures the selected guard instead of a mutable grant-property lookup',
    }),
    'connection': ('connection.ts', '...admitGeneration === undefined ? {} : { admitGeneration },',
                   '...{},', {
        'threads admission through the actual connection startup owner',
        'empty admitted tool set does not expose other context channels',
        'uses the same admission hook on actual SDK tool-list notifications',
    }),
}


def mutations() -> dict:
    source = CACHE / 'mcp-donor'
    before = {p.name: p.read_bytes() for p in source.glob('*.ts')}
    destination = CACHE / 'mcp-mutant'
    destination.mkdir(exist_ok=True)
    results = {}
    for name, (file, old, new, expected) in MUTATIONS.items():
        for key, data in before.items():
            (destination / key).write_bytes(data)
        text = before[file].decode()
        assert text.count(old) == 1, f'{name}: mutation target not unique'
        changed = text.replace(old, new).encode()
        (destination / file).write_bytes(changed)
        results[name] = {**suite(f'mcp-mutant-final-{name}', 'mutant', expected),
                         'mutant_sha256': digest(changed), 'killed': True}
    assert before == {p.name: p.read_bytes() for p in source.glob('*.ts')}
    return results


def stdio_checks() -> dict:
    """Real SDK subprocess checks, preserving sibling-probe and session settlement."""
    def collect(name: str, source: str, expected: set[str]) -> dict:
        result = suite(name, source, expected, stdio=True)
        raw = (CACHE / 'stdio-observations.json').read_bytes()
        rows = json.loads(raw)
        assert len(rows) == 12, 'Missing stdio cleanup evidence'
        assert all(row['childCount'] == 2 and row['childAbsentAfterDispose']
                   and row['inputsUnchanged'] for row in rows)
        (CACHE / f'{name}-observations.json').write_bytes(raw)
        return {**result, 'observations_sha256': digest(raw), 'observations': rows,
                'all_observed_children_settled': True}

    patched = collect('mcp-stdio-patched', 'donor', set())
    source = CACHE / 'mcp-donor'
    before = {p.name: p.read_bytes() for p in source.glob('*.ts')}
    destination = CACHE / 'mcp-mutant'
    destination.mkdir(exist_ok=True)
    for name, data in before.items():
        (destination / name).write_bytes(data)
    text = before['connection.ts'].decode()
    old = 'transport = createTransport(config, toolOnly)'
    assert text.count(old) == 1
    mutant = text.replace(old, 'transport = createTransport(config)').encode()
    (destination / 'connection.ts').write_bytes(mutant)
    expected = {'host-admitted stdio excludes unapproved ambient configuration',
                'host-admitted stdio excludes ambient Node startup options'}
    rejected = collect('mcp-stdio-environment-mutant', 'mutant', expected)
    assert before == {p.name: p.read_bytes() for p in source.glob('*.ts')}
    sdk_root = ROOT / 'node_modules/@modelcontextprotocol/client/dist'
    return {'patched': patched, 'environment_mutant': {**rejected, 'killed': True,
             'mutant_sha256': digest(mutant)},
            'sdk_executable_sha256': {name: digest((sdk_root / name).read_bytes())
                                      for name in ['index.mjs', 'stdio.mjs']},
            'scope': 'Synthetic disk inputs, SDK probe plus session; no model, ACP parent or OS confinement'}


def preparation_checks() -> dict:
    result = subprocess.run([sys.executable, '-B', 'mcp-preparation.test.py'],
                            cwd=ROOT, env=ENV, capture_output=True, text=True, timeout=30)
    output = result.stdout + result.stderr
    (CACHE / 'mcp-preparation-tests.log').write_text(output)
    assert result.returncode == 0 and 'Ran 6 tests' in output and '\nOK\n' in output
    return {'tests': 6, 'passed': 6, 'exit_code': 0, 'log_sha256': digest(output.encode())}


def profile_observations() -> dict:
    raw = (CACHE / 'profile-observations.json').read_bytes()
    observed = json.loads(raw)
    assert observed and all(x['childrenAbsent'] and x['inputsUnchanged'] for x in observed)
    pids = [pid for x in observed for pid in x['pids']]
    for pid in pids:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            pass
        else:
            raise AssertionError(f'Profile fixture process remains: {pid}')
    useful = [x for x in observed if x.get('workload', {}).get('search')]
    assert len(useful) == 1
    assert useful[0]['workload']['read']['nonce'] == useful[0]['nonce']
    assert useful[0]['workload']['search']['nonce'] == useful[0]['nonce']
    return {'observations_sha256': digest(raw), 'fixture_pids': pids,
            'all_recorded_children_absent': True, 'inputs_unchanged': True,
            'useful_workload': useful[0]}


PROFILE_MUTATIONS = {
    'startup_policy': ('index.ts',
        'if (fixedConfig.failOnStartupError !== true || fixedConfig.reconnect?.enabled !== false)',
        'if (false)', {
            'admitted plugin refuses permissive startup before process creation',
            'admitted plugin refuses implicit reconnect before process creation',
            'admitted plugin refuses enabled reconnect before process creation',
        }),
    'admission_wiring': ('index.ts',
        'const connection = startConnection(ctx, config, reconnect, admitGeneration)',
        'const connection = startConnection(ctx, config, reconnect, undefined)', {
            'public admitted plugin activates the real read path with only selected tools',
            'Mastermind runtime profile performs preflight then activates the actual read process',
            'admission refusal rolls back namespace so a later explicit instance can activate',
        }),
    'required_preflight': ('dsh_tool_profile.mjs',
        'await qualifyLoadedDispatchRuntime(ctx, { signal })',
        'void ctx // deliberately skipped preflight', {
            'Mastermind runtime profile rejects disabled dispatch enforcement before spawning',
            'Mastermind runtime profile rejects deny-all false readiness before spawning',
            'Mastermind runtime profile cancellation during preflight never starts a process',
            'Mastermind runtime profile snapshots startup config before asynchronous preflight',
        }),
    'startup_snapshot': ('dsh_tool_profile.mjs',
        'const snapshot = structuredClone(config)', 'const snapshot = config', {
            'Mastermind runtime profile snapshots startup config before asynchronous preflight',
        }),
}


def profile_checks() -> dict:
    owner = ROOT.parents[2] / 'integrations/acp_worker'
    originals = {name: (owner / name).read_bytes() for name in [
        'dsh_tool_profile.mjs', 'dsh_dispatch_preflight.mjs']}
    donor = {p.name: p.read_bytes() for p in (CACHE / 'mcp-donor').glob('*.ts')}
    positive = {**suite('profile-final', 'donor', set(), profile=True),
                **profile_observations()}
    mutants = {}
    for name, (file, old, new, expected) in PROFILE_MUTATIONS.items():
        is_donor = file.endswith('.ts')
        originals_for_mutant = donor if is_donor else originals
        dest = CACHE / ('mcp-mutant' if is_donor else 'profile-mutant')
        dest.mkdir(exist_ok=True)
        for key, data in originals_for_mutant.items():
            (dest / key).write_bytes(data)
        text = originals_for_mutant[file].decode()
        assert text.count(old) == 1, f'{name}: ambiguous mutation target'
        changed = text.replace(old, new).encode(); (dest / file).write_bytes(changed)
        mutants[name] = {**suite('profile-mutant-' + name,
            'mutant' if is_donor else 'donor', expected, profile=True,
            profile_source='runtime' if is_donor else 'mutant'),
            **profile_observations(), 'mutant_sha256': digest(changed), 'killed': True}
    assert originals == {name: (owner / name).read_bytes() for name in originals}
    assert donor == {p.name: p.read_bytes() for p in (CACHE / 'mcp-donor').glob('*.ts')}
    return {'positive': positive, 'mutants': mutants,
            'scope': 'Real Cordis plugin and Mastermind source profile + synthetic MCP process; not installed ACP or Executive acceptance'}


def artifact_node(name: str, argv: list[str]) -> dict:
    result = subprocess.run([NODE, *argv], cwd=ROOT, env=ENV,
                            capture_output=True, text=True, timeout=60, check=False)
    raw = result.stdout + result.stderr
    (CACHE / (name + '.log')).write_text(raw)
    assert result.returncode == 0 and not result.stderr, f'{name}: native artifact execution failed'
    return {'exit_code': result.returncode, 'stderr_empty': True, 'log_sha256': digest(raw.encode())}


def native_artifact_checks() -> dict:
    first = artifact_node('profile-artifact-build', ['build-profile.mjs'])
    before = json.loads((CACHE / 'profile-build-result.json').read_text())
    second = artifact_node('profile-artifact-rebuild', ['build-profile.mjs'])
    built = json.loads((CACHE / 'profile-build-result.json').read_text())
    assert before['files'] == built['files'] and before['input_sha256'] == built['input_sha256']
    for name, expected in built['input_sha256'].items():
        assert digest((ROOT / name).read_bytes()) == expected, name
    path = Path(built['artifact'])
    assert not path.is_absolute() and '..' not in path.parts
    assert digest((CACHE / path).read_bytes()) == built['artifact_sha256']
    results = {}
    for scenario in ['normal', 'disabled-core', 'startup-refused', 'pre-aborted']:
        run = artifact_node('native-profile-' + scenario, ['native-profile-canary.mjs', scenario])
        raw = (CACHE / ('native-profile-' + scenario + '.json')).read_bytes()
        observed = json.loads(raw)
        assert observed['success'] and observed['scenario'] == scenario
        assert observed['artifact_sha256'] == built['artifact_sha256']
        assert observed['fixture_children_absent'] and observed['inputs_unchanged']
        for pid in observed['fixture_pids']:
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                pass
            else:
                raise AssertionError(f'Native artifact fixture remains: {pid}')
        results[scenario] = {**run, 'receipt_sha256': digest(raw), 'observation': observed}
    return {'build': built, 'build_run': first, 'rebuild_run': second,
            'repeat_build_identical': True, 'scenarios': results,
            'scope': 'Actual built module imported by plain Node, no Vitest alias/loader; test-local external dependencies, not installed ACP'}


def main() -> dict:
    core_supply = prepare_core(download=False)
    mcp_supply = prepare(download=False)
    report = {
        'schema': 'mastermind.dsh_mcp_admission_verification.v1',
        'generated_at': dt.datetime.now(dt.timezone.utc).isoformat(),
        'node': subprocess.run([NODE, '--version'], capture_output=True, text=True,
                               env=ENV, timeout=5, check=True).stdout.strip(),
        'node_sha256': digest(Path(NODE).resolve().read_bytes()),
        'platform': platform.system(), 'architecture': platform.machine(),
        'scope': 'Real MCP SDK protocol and donor bridge; no model/installed-worker/Executive-parent proof',
        'core_supply': core_supply, 'mcp_supply': mcp_supply,
        'model_requests': 0, 'network_transport': 'OFFICIAL_IN_MEMORY_MCP_AND_REAL_LOCAL_STDIO',
        'independent_review': 'NOT_PERFORMED', 'installed': False,
    }
    report['targeted'] = {
        'pristine': suite('mcp-baseline-final', 'pristine', EXPECTED_RED),
        'patched': suite('mcp-patched-final', 'donor', set()),
    }
    report['observations'] = json.loads((CACHE / 'mcp-observations-donor.json').read_text())
    nonce, notification = report['observations']
    assert nonce['result']['content'] == [{'type': 'text', 'text': nonce['sourceNonce']}]
    assert nonce['calls'] == {'read': 1, 'write': 0}
    assert nonce['exposed'] == [nonce['publicName']]
    assert notification['generationsObserved'] >= 2 and notification['calls'] == 1
    assert notification['exposedAfterRevocation'] == []
    report['upstream'] = {mode: suite(f'mcp-upstream-final-{mode}', mode, set(), upstream=True)
                          for mode in ['pristine', 'donor']}
    report['worker_profile'] = profile_checks()
    report['native_artifact'] = native_artifact_checks()
    report['typecheck'] = typecheck()
    report['mutations'] = mutations()
    report['stdio'] = stdio_checks()
    report['preparation'] = preparation_checks()
    report['input_sha256'] = {name: digest((ROOT / name).read_bytes()) for name in [
        'mcp-generation-admission.patch', 'mcp-manifest.json', 'mcp-admission.test.mjs',
        'mcp-context-boundary.test.mjs', 'mcp-stdio.test.mjs', 'stdio-fixture-server.mjs',
        'prepare_mcp.py', 'verify_mcp.py', 'vitest.mcp.config.mjs', 'tsconfig.mcp.json',
        'mcp-preparation.test.py',
        'profile-startup.test.mjs', 'build-profile.mjs', 'native-profile-canary.mjs',
        '../../../integrations/acp_worker/dsh_tool_profile.mjs',
        '../../../integrations/acp_worker/dsh_dispatch_preflight.mjs',
        'package.json', 'package-lock.json', 'donor-manifest.json', 'strict-dispatch-binding.patch']}
    report['success'] = True
    return report


if __name__ == '__main__':
    report = main()
    destination = CACHE / 'mcp-verification-report.json'
    destination.write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    print(json.dumps({'success': True, 'mcp_tests': report['targeted']['patched']['passed'],
                      'upstream_tests': report['upstream']['donor']['passed'],
                      'stdio_tests': report['stdio']['patched']['passed'],
                      'profile_tests': report['worker_profile']['positive']['passed'],
                      'native_artifact_scenarios': len(report['native_artifact']['scenarios']),
                      'report': str(destination)}, indent=2))

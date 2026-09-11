"""Offline verification in a fresh, caller-selected directory. No network or browser.

Supply the existing Terminal analytics.ts, not a new profile implementation.
Node.js 22 and TypeScript 5.8.3 were used for the recorded run. The mutation
runner fails rather than silently skipping if compiler output changes.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

PROFILE_BLOB = 'dd6abc4e177ff4870d2b64b927c73d7ea430e2a3'
ADAPTER_SHA = 'c1fd0700df0385560103431c32d2d8598fd8971a97318b8a93f6d0d777d65dbb'
ROOT = Path(__file__).resolve().parent

def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def execute(args: list[str], cwd: Path, stem: str, timeout: int = 90) -> None:
    completed = subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    (cwd / 'results' / (stem + '.stdout.txt')).write_text(completed.stdout)
    (cwd / 'results' / (stem + '.stderr.txt')).write_text(completed.stderr)
    if completed.returncode:
        raise RuntimeError(f'{stem} exited {completed.returncode}; read results/{stem}.stderr.txt')

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--terminal-source', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True, help='Must not already exist.')
    args = parser.parse_args()
    if not shutil.which('node') or not shutil.which('tsc'):
        raise RuntimeError('Node.js and TypeScript must already be installed; this runner does not install them.')
    dependency = args.terminal_source.resolve(strict=True)
    body = dependency.read_bytes()
    blob = hashlib.sha1(b'blob ' + str(len(body)).encode() + b'\0' + body).hexdigest()
    if blob != PROFILE_BLOB:
        raise RuntimeError('Terminal profile source differs from the audited blob; review the new dependency first.')
    adapter = ROOT / 'auctionContext.ts'
    if not adapter.exists():
        adapter = ROOT / 'source/auctionContext.ts'
    if sha(adapter) != ADAPTER_SHA:
        raise RuntimeError('Adapter differs from the reviewed source. This receipt would not apply.')
    out = args.out.absolute()
    out.mkdir(parents=True, exist_ok=False)
    (out / 'source').mkdir()
    (out / 'results').mkdir()
    # A private verification package, never an installed product directory.
    (out / 'package.json').write_text('{"private":true,"type":"commonjs"}\n')
    shutil.copyfile(adapter, out / 'source/auctionContext.ts')
    shutil.copyfile(dependency, out / 'source/terminal_analytics_pinned.ts')
    for name in ['test_context.cjs', 'property_check.cjs', 'mutation_check.py']:
        shutil.copyfile(ROOT / name, out / name)
    execute(['tsc', 'source/auctionContext.ts', 'source/terminal_analytics_pinned.ts',
             '--strict', '--target', 'ES2022', '--module', 'NodeNext',
             '--moduleResolution', 'NodeNext', '--outDir', 'compiled', '--skipLibCheck'], out, 'compile')
    execute(['node', 'test_context.cjs'], out, 'contracts')
    execute(['node', 'property_check.cjs'], out, 'properties')
    execute([sys.executable, 'mutation_check.py'], out, 'mutations')
    reports = {name: json.loads((out / 'results' / name).read_text()) for name in
               ['context_contract.json', 'property_report.json', 'mutation_report.json']}
    if any(report['status'] != 'PASS' for report in reports.values()):
        raise RuntimeError('At least one semantic result failed despite successful tool exit.')
    result = {
        'status': 'PASS', 'scope': 'Offline research adapter; no market, browser or production proof',
        'adapter_sha256': ADAPTER_SHA, 'terminal_source_git_blob': blob,
        'node': subprocess.check_output(['node', '--version'], text=True).strip(),
        'typescript': subprocess.check_output(['tsc', '--version'], text=True).strip(),
        'contracts_passed': reports['context_contract.json']['passed'],
        'contracts_total': reports['context_contract.json']['total'],
        'synthetic_scenarios': reports['property_report.json']['scenarios'],
        'synthetic_assertions': reports['property_report.json']['assertions'],
        'mutants_caught': reports['mutation_report.json']['caught'],
        'mutants_total': reports['mutation_report.json']['mutants'],
        'files': {str(p.relative_to(out)): sha(p) for p in sorted(out.rglob('*')) if p.is_file()
                  and 'mutants' not in p.parts},
        'no_network_or_installs': True, 'no_browser_attempt': True,
    }
    (out / 'verification_receipt.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({k: v for k, v in result.items() if k != 'files'}, indent=2))

if __name__ == '__main__':
    main()

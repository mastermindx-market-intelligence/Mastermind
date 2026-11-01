#!/usr/bin/env python3
"""Validate this research pack's structure, not the product or source truth.

No network, credentials, repository mutation, or product execution. By default
prints a read-only report. --write-receipt writes only this pack's validation
receipt and content manifest. --root supports isolated negative fixtures.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit

REQUIRED_DOCS = [
    'README.md', 'FABLE_BRIEF.md', '01_CENSUS_AND_AUDIT.md',
    '02_OPEN_MASTERPLAN.md', '03_SYSTEM_AND_PRODUCT_DESIGN.md',
    '04_ACCEPTANCE_AND_EVALUATION.md', '05_RESEARCH_AND_HARNESS_OPTIONS.md',
    '06_FABLE_RESOURCE_MAP_AND_KICKOFF.md', '07_EVIDENCE_AND_HANDOFF.md',
    '08_FABRIC_SOURCE_AUDIT_ADJUDICATION.md',
]
EXPECTED_IDS = {f'{prefix}{n}' for prefix, count in
                [('E', 12), ('F', 7), ('G', 8), ('A', 6), ('C', 5), ('H', 8)]
                for n in range(1, count + 1)}
SHA40 = re.compile(r'^[0-9a-f]{40}$')
SECRET_PATTERNS = [
    re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
    re.compile(r'\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{30,}\b'),
    re.compile(r'\bAKIA[A-Z0-9]{16}\b'),
    re.compile(r'\beyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\b'),
]


def validate(root: Path) -> tuple[dict, dict]:
    errors: list[str] = []
    warnings: list[str] = []
    stats: dict[str, int] = {}

    def require(ok: bool, message: str) -> None:
        if not ok:
            errors.append(message)

    def load(relative: str) -> dict:
        try:
            return json.loads((root / relative).read_text(encoding='utf-8'))
        except (OSError, ValueError) as exc:
            errors.append(f'{relative}: {exc}')
            return {}

    for name in REQUIRED_DOCS:
        require((root / name).is_file(), f'Missing required document: {name}')

    prs = load('evidence/pr_snapshot.json').get('pull_requests', [])
    stats['selected_prs'] = len(prs)
    require(len(prs) == 70, 'Expected 70 selected PR records')
    require(len({(p.get('repository'), p.get('number')) for p in prs}) == len(prs),
            'Duplicate PR identity')
    for p in prs:
        for field in ['head', 'base']:
            require(bool(SHA40.fullmatch(str(p.get(field, '')))),
                    f'Invalid {field} SHA in PR {p.get("number")}')
    try:
        with (root / 'evidence/pr_snapshot.csv').open(newline='', encoding='utf-8') as f:
            csv_rows = list(csv.DictReader(f))
        require(len(csv_rows) == len(prs), 'CSV/JSON PR count mismatch')
        require({(p['repository'], int(p['number']), p['head']) for p in csv_rows}
                == {(p['repository'], p['number'], p['head']) for p in prs},
                'CSV/JSON PR identity mismatch')
    except (OSError, KeyError, ValueError) as exc:
        errors.append(f'PR CSV: {exc}')

    ws = load('evidence/workstream_snapshot.json').get('workstreams', [])
    stats['workstreams'] = len(ws)
    require(len(ws) == 15 and len({r.get('key') for r in ws}) == 15,
            'Expected 15 unique workstreams')
    for r in ws:
        require(bool(SHA40.fullmatch(str(r.get('source_commit', '')))),
                f'Invalid workstream source SHA: {r.get("key")}')

    caps = load('evidence/original_46_capabilities.json').get('capabilities', [])
    stats['original_capabilities'] = len(caps)
    require(len(caps) == 46 and {r.get('id') for r in caps} == EXPECTED_IDS,
            'Original capability denominator differs from 46 stable IDs')
    census = (root / '01_CENSUS_AND_AUDIT.md').read_text(encoding='utf-8') if (root / '01_CENSUS_AND_AUDIT.md').exists() else ''
    ids = re.findall(r'^\| ([EFGACH][0-9]+) \|', census, re.MULTILINE)
    require(len(ids) == 46 and set(ids) == EXPECTED_IDS,
            'Census does not cover exactly the 46 original IDs')

    tests = load('evidence/original_r2_obligations.json').get('obligations', [])
    stats['original_r2_obligations'] = len(tests)
    require(len(tests) == 30, 'Expected 30 original R2 obligations')
    acceptance = (root / '04_ACCEPTANCE_AND_EVALUATION.md').read_text(encoding='utf-8') if (root / '04_ACCEPTANCE_AND_EVALUATION.md').exists() else ''
    for t in tests:
        require(t.get('original_test', '') in acceptance,
                f'Acceptance crosswalk missing: {t.get("original_test")}')

    checks = load('evidence/check_snapshot.json').get('pull_requests', [])
    stats['check_candidates'] = len(checks)
    require(len(checks) == 6, 'Expected six exact-head check snapshots')
    for c in checks:
        require(all(r.get('head_sha') == c.get('head') for r in c.get('checks', [])),
                f'Check head mismatch: PR {c.get("pr_number")}')

    candidates = load('evidence/candidate_files.json').get('candidates', [])
    stats['file_candidates'] = len(candidates)
    require(len(candidates) == 14, 'Expected 14 candidate file inventories')
    for c in candidates:
        require(c.get('head_matches_snapshot') == (c.get('snapshot_head') == c.get('current_head_readback')),
                f'Inconsistent drift classification: PR {c.get("pr_number")}')
        if not c.get('head_matches_snapshot') or not c.get('base_matches_snapshot'):
            warnings.append(f'PR {c.get("pr_number")} drifted; do not infer original file projection currentness')

    audit = load('evidence/fabric_audit_receipt.json')
    require(audit.get('observed_state') == 'TERMINAL' and audit.get('root_verified') is True,
            'Audit terminal/root observation missing')
    require(audit.get('raw_report_accepted') is False,
            'Raw source-audit report must not be represented as wholesale accepted')

    local_links = external_links = word_count = 0
    manifest: dict[str, str] = {}
    for p in sorted(root.rglob('*')):
        if p.is_symlink():
            errors.append(f'Symlink not allowed in research pack: {p.relative_to(root)}')
            continue
        if not p.is_file() or '__pycache__' in p.parts:
            continue
        rel = p.relative_to(root).as_posix()
        if rel not in {'evidence/validation_receipt.json', 'evidence/content_manifest.json'}:
            manifest[rel] = hashlib.sha256(p.read_bytes()).hexdigest()
        if p.suffix not in {'.md', '.json', '.csv'}:
            continue
        require(b'\r\n' not in p.read_bytes(), f'CRLF line endings in publication text: {rel}')
        text = p.read_text(encoding='utf-8')
        for pattern in SECRET_PATTERNS:
            require(pattern.search(text) is None, f'Possible secret/private-key material: {rel}')
        if p.suffix != '.md':
            continue
        word_count += len(text.split())
        for target in re.findall(r'\[[^\]\n]+\]\(([^)\n]+)\)', text):
            url = target.split(' ', 1)[0].strip('<>')
            parsed = urlsplit(url)
            if parsed.scheme in {'http', 'https', 'mailto'}:
                external_links += 1
                continue
            if not parsed.path:
                continue
            local_links += 1
            resolved = (p.parent / unquote(parsed.path)).resolve()
            require(resolved.is_relative_to(root), f'Local link escapes pack: {rel} -> {target}')
            require(resolved.exists(), f'Broken local link: {rel} -> {target}')
    stats.update({'required_markdown_documents':len(REQUIRED_DOCS),
                  'markdown_word_count':word_count, 'local_links_checked':local_links,
                  'external_links_not_network_validated':external_links,
                  'manifest_files':len(manifest)})
    result = {'status':'PASS' if not errors else 'FAIL',
              'observed_at_utc':dt.datetime.now(dt.timezone.utc).isoformat(),
              'scope':'Static research-artifact structure and coverage only; not product, source-truth, security or independent review acceptance',
              'statistics':stats, 'errors':errors, 'warnings':warnings}
    return result, manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument('--write-receipt', action='store_true')
    args = parser.parse_args()
    root = args.root.resolve(strict=True)
    result, manifest = validate(root)
    if args.write_receipt:
        (root / 'evidence').mkdir(exist_ok=True)
        (root / 'evidence/validation_receipt.json').write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
        (root / 'evidence/content_manifest.json').write_text(json.dumps({'hash':'sha256','excludes':['evidence/validation_receipt.json','evidence/content_manifest.json'],'files':manifest}, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(result, indent=2))
    return 0 if result['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())

"""Pass through the incumbent Agent OS context compiler; no new retrieval/store."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile

from ops.fabric_launch.context import LaunchInputError

OWNER_ROOT = Path('/Users/chriswong/Documents/Cluade/macro-main')
MAX_BUNDLE_BYTES = 128 * 1024


def validate_bundle(raw, workstream):
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_BUNDLE_BYTES:
        raise LaunchInputError('AGENTOS_BUNDLE_SIZE_INVALID')
    def unique(pairs):
        result={}
        for key,value in pairs:
            if key in result:raise LaunchInputError('AGENTOS_DUPLICATE_KEY')
            result[key]=value
        return result
    def nonfinite(_):
        raise LaunchInputError('AGENTOS_NONFINITE_JSON')
    try:
        bundle=json.loads(raw.decode(),object_pairs_hook=unique,
                          parse_constant=nonfinite)
    except (ValueError,UnicodeError,RecursionError) as exc:
        if isinstance(exc,LaunchInputError):raise
        raise LaunchInputError('AGENTOS_BUNDLE_MALFORMED') from None
    if type(bundle) is not dict or bundle.get('schema')!='context_bundle.v1':
        raise LaunchInputError('AGENTOS_BUNDLE_SCHEMA_INVALID')
    target=bundle.get('target')
    expected='WS:'+workstream.removeprefix('WS:').removeprefix('WS-')
    if type(target) is not dict or target.get('workstream')!=expected or bundle.get('no_answer_reason') is not None:
        raise LaunchInputError('AGENTOS_EXACT_WORKSTREAM_UNRESOLVED')
    for field in ('sections','degraded','excluded','omitted_due_to_budget'):
        if type(bundle.get(field)) is not list:
            raise LaunchInputError('AGENTOS_BUNDLE_ACCOUNTING_MISSING')
    # Return the owner's exact bytes, including mandatory over-budget content and
    # accounting tails. Do not re-rank, summarize, drop constraints or hide gaps.
    return bundle


def read_context(workstream, budget=4000, *, owner_root=OWNER_ROOT, run=subprocess.run):
    if type(workstream) is not str or not re.fullmatch(r'(?:WS[:-])?[A-Z][A-Z0-9-]{0,95}',workstream):
        raise LaunchInputError('AGENTOS_WORKSTREAM_INVALID')
    if type(budget) is not int or not 800 <= budget <= 12000:
        raise LaunchInputError('AGENTOS_BUDGET_INVALID')
    root=Path(owner_root)
    script=root/'scripts/agentos.py'
    if script.is_symlink() or not script.is_file():
        raise LaunchInputError('AGENTOS_OWNER_UNAVAILABLE')
    before=hashlib.sha256(script.read_bytes()).hexdigest()
    with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
        try:
            result=run([sys.executable,str(script),'compile-context','--workstream',workstream,
                        '--json','--budget',str(budget)],cwd=root,stdout=out,stderr=err,
                       timeout=25,check=False)
        except subprocess.TimeoutExpired:
            raise LaunchInputError('AGENTOS_CONTEXT_READ_TIMEOUT') from None
        if result.returncode!=0:
            raise LaunchInputError('AGENTOS_CONTEXT_READ_REFUSED')
        out.seek(0);raw=out.read(MAX_BUNDLE_BYTES+1)
    if hashlib.sha256(script.read_bytes()).hexdigest()!=before:
        raise LaunchInputError('AGENTOS_OWNER_SOURCE_CHANGED')
    bundle=validate_bundle(raw,workstream)
    receipt={'owner':'agent_os','source_script_sha256':before,
             'bundle_sha256':hashlib.sha256(raw).hexdigest(),
             'workstream':bundle['target']['workstream'],
             'repo_sha':bundle.get('repo_sha'),'generated_at':bundle.get('generated_at'),
             'degraded_count':len(bundle['degraded']),
             'omitted_count':len(bundle['omitted_due_to_budget']),
             'execution_authority':False}
    return raw,receipt

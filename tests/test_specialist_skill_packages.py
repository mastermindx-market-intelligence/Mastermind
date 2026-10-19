"""Static source/package checks, explicitly not model-behavior or rollout proof."""
from __future__ import annotations
import importlib.util
import io
import json
from pathlib import Path
import re
import subprocess
import zipfile

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('specialist_packager', ROOT / 'scripts/package_mastermind_specialists.py')
assert spec and spec.loader
pack = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pack)
NAMES = pack.SPECIALISTS + ('agent-pools',)


def sources(include_native=False):
    return {path: (ROOT/path).read_bytes() for path in pack.source_paths(include_native)}


@pytest.mark.parametrize('name', NAMES)
def test_skill_format_and_reference_closure(name):
    root=ROOT/'skills'/name
    text=(root/'SKILL.md').read_text()
    assert len(text.encode()) < 9000
    assert len(text.splitlines()) < 150
    assert text.startswith(f'---\nname: {name}\ndescription: ')
    front, body=text[4:].split('\n---\n', 1)
    assert [line.split(':',1)[0] for line in front.splitlines()] == ['name','description']
    description=front.split('\ndescription: ',1)[1]
    assert 80 <= len(description) <= 1024
    assert 'Do not' in description or 'do not' in description
    assert 'EFFECT_UNKNOWN' in body and 'original operation and carrier' in body
    assert '## ' in body and 'references/cases.md' in body
    for target in re.findall(r'\]\(([^)]+)\)', body):
        assert not target.startswith(('http:', 'https:', '/'))
        path=root/target
        assert path.is_file() and not path.is_symlink()
        assert root.resolve() in path.resolve().parents
    assert 'display_name:' in (root/'agents/openai.yaml').read_text()
    assert not list(root.rglob('*.py'))
    assert 'TODO' not in text


def test_domain_boundaries_are_explicit():
    def body(n): return (ROOT/'skills'/n/'SKILL.md').read_text().lower()
    assert 'merge-group validation' in body('mastermind-ci-triage')
    assert 'green ci, merged code and user acceptance' in body('mastermind-ci-triage')
    assert 'persistence readback' in body('mastermind-product-path-proof')
    assert 'unknown must not become zero' in body('mastermind-product-path-proof')
    assert 'later restatement' in body('mastermind-market-source-validation')
    assert 'one origin' in body('mastermind-market-source-validation')
    assert 'untouched test' in body('mastermind-quant-validation')
    assert 'purge intersecting' in body('mastermind-quant-validation')
    assert 'mitigation and root cause separately' in body('mastermind-telemetry-investigation')
    assert 'missing telemetry' in body('mastermind-telemetry-investigation')


def test_native_routing_has_no_live_inventory_or_spawn_bypass():
    text=(ROOT/'skills/agent-pools/SKILL.md').read_text()
    assert not re.search(r'\b20\d\d-\d\d-\d\d\b', text)
    assert '| Provider |' not in text and 'pool run ' not in text
    assert '--pool grok' not in text and 'cap / account' not in text.lower()
    assert 'does not authorize a Web shell handoff' in text
    assert 'Never open a credential file' in text
    assert 'original root, actual parent' in text


@pytest.mark.parametrize('include_native', [False, True])
def test_deterministic_package_and_truthful_receipt(include_native):
    files=sources(include_native)
    result=pack.assemble(files, 'a'*40, include_native_routing=include_native)
    assert pack.zip_bytes(result) == pack.zip_bytes(result)
    receipt=json.loads(result['BUILD.json'])
    assert receipt['state']=='PACKAGED_NOT_INSTALLED'
    assert receipt['native_skill_attested'] is False
    assert receipt['execution_authority'] is False
    assert set(receipt['canonical_source_files']) == set(files)
    assert ('skills/agent-pools/SKILL.md' in result) is include_native
    for directory in ('.codex-plugin','.claude-plugin'):
        manifest=json.loads(result[directory+'/plugin.json'])
        assert manifest['skills']=='./skills/'
        assert not {'mcpServers','hooks','permissions','apps'} & set(manifest)
    with zipfile.ZipFile(io.BytesIO(pack.zip_bytes(result))) as archive:
        assert len(archive.namelist())==len(result)
        assert all(i.filename.startswith('mastermind-specialists/') for i in archive.infolist())
        assert all(i.date_time==(1980,1,1,0,0,0) for i in archive.infolist())


@pytest.mark.parametrize('sha', ['master','a'*39,'A'*40,'a'*41,'../bad',''])
def test_mutable_or_invalid_ref_is_refused(sha):
    with pytest.raises(ValueError,match='EXACT_COMMIT_REQUIRED'):
        pack.assemble(sources(), sha)


@pytest.mark.parametrize('mutation', ['missing','extra','wrong_name','oversized','invalid_utf8'])
def test_changed_source_census_or_content_is_refused(mutation):
    files=sources()
    key='skills/mastermind-ci-triage/SKILL.md'
    if mutation=='missing': files.pop(key)
    elif mutation=='extra': files['skills/extra/SKILL.md']=b'not allowed'
    elif mutation=='wrong_name': files[key]=files[key].replace(b'name: mastermind-ci-triage',b'name: wrong',1)
    elif mutation=='oversized': files[key]=b'x'*(pack.MAX_FILE_BYTES+1)
    else: files[key]=b'\xff'
    with pytest.raises((ValueError,UnicodeError)):
        pack.assemble(files,'a'*40)


@pytest.mark.parametrize('path', ['../escape','/absolute','x/../../escape','x\\escape',''])
def test_zip_path_escape_is_refused(path):
    with pytest.raises(ValueError,match='ARCHIVE_PATH_INVALID'):
        pack.zip_bytes({path:b'bad'})


def test_real_git_commit_source_and_dirty_worktree_isolation(tmp_path):
    repo=tmp_path/'repo'; repo.mkdir()
    def git(*args):
        return subprocess.run(['git', *args], cwd=repo, check=True, capture_output=True).stdout.decode().strip()
    git('init','-q')
    git('config','user.name','Skill Test')
    git('config','user.email','skill-test@example.invalid')
    for relative, data in sources(True).items():
        path=repo/relative; path.parent.mkdir(parents=True,exist_ok=True); path.write_bytes(data)
    git('add','skills'); git('commit','-qm','fixture')
    sha=git('rev-parse','HEAD')
    expected=sources()
    (repo/'skills/mastermind-ci-triage/SKILL.md').write_text('uncommitted replacement')
    assert pack.read_commit_files(repo,sha)==expected
    # Exact regular-file closure refuses a symlink even if Git can return its blob.
    path=repo/'skills/mastermind-ci-triage/SKILL.md'; path.unlink(); path.symlink_to('/tmp/untrusted')
    git('add',str(path.relative_to(repo))); git('commit','-qm','symlink fixture')
    with pytest.raises(ValueError,match='SOURCE_NOT_REGULAR_TEXT'):
        pack.read_commit_files(repo,git('rev-parse','HEAD'))


def test_eval_fixture_has_positive_negative_missing_and_adversarial_cases():
    fixture=json.loads((ROOT/'tests/fixtures/specialist_skill_cases.json').read_text())
    assert fixture['model_evaluation_executed'] is False
    assert fixture['scope']=='evaluation_design_not_results'
    cases=fixture['cases']
    assert len({c['id'] for c in cases})==len(cases)
    for name in NAMES:
        group=[c for c in cases if c['skill']==name]
        assert {c['kind'] for c in group}=={'positive','negative','missing_evidence','adversarial'}
        assert all(c['prompt'] and c['required_behavior'] and c['must_not'] for c in group)
        assert next(c for c in group if c['kind']=='negative')['should_activate'] is False


def test_web_manifest_has_display_name_without_polluting_claude_schema():
    artifact = pack.assemble(sources(), 'a' * 40)
    codex = json.loads(artifact['.codex-plugin/plugin.json'])
    claude = json.loads(artifact['.claude-plugin/plugin.json'])
    assert codex['interface']['displayName'] == 'Mastermind Specialists'
    assert codex['interface']['shortDescription'].strip()
    assert 'interface' not in claude
    assert {key: value for key, value in codex.items() if key != 'interface'} == claude

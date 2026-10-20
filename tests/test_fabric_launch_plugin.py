import io
import hashlib
import json
import zipfile
import pytest
from ops.fabric_launch import plugin as p
from ops.fabric_launch import install as source_install


def inputs():
    files = {'research/worker_craft/mastermind-craft/SKILL.md':b'unchanged Craft',
             'research/worker_craft/mastermind-craft/references/reviewer.md':b'unchanged review',
             'skills/mastermind-worker-bootstrap/SKILL.md':b'boot',
             'ops/fabric_launch/context.py':b'not copied to plugin'}
    for role_file in p.ORCHESTRATION_ROLE_FILES:
        files['skills/mastermind-fabric-orchestration/'+role_file] = ('role:'+role_file).encode()
    return files


def test_generated_distribution_preserves_single_source_bytes():
    files=p.assemble(inputs(),'a'*40)
    assert files['skills/mastermind-craft/SKILL.md']==b'unchanged Craft'
    assert files['skills/mastermind-craft/references/reviewer.md']==b'unchanged review'
    assert 'ops/fabric_launch/context.py' not in files
    for role_file in p.ORCHESTRATION_ROLE_FILES:
        key = 'skills/mastermind-fabric-orchestration/'+role_file
        assert files[key] == inputs()[key]

    build=json.loads(files['BUILD.json'])
    assert build['source_state']=='SOURCE_CANDIDATE'
    assert build['native_skill_attested'] is False and build['execution_authority'] is False
    assert build['mcp_servers']==[] and '.mcp.json' not in files
    src = build['canonical_source_files']
    for role_file in p.ORCHESTRATION_ROLE_FILES:
        key = 'skills/mastermind-fabric-orchestration/'+role_file
        assert src[key] == {'path': key, 'sha256': hashlib.sha256(inputs()[key]).hexdigest()}



def test_optional_mcp_contains_only_public_docs_without_credentials_or_shell():
    files=p.assemble(inputs(),'a'*40,docs=True)
    config=json.loads(files['.mcp.json'])
    assert config=={'mcpServers':{'openaiDeveloperDocs':{'type':'http','url':'https://developers.openai.com/mcp'}}}
    assert json.loads(files['.codex-plugin/plugin.json'])['mcpServers']=='./.mcp.json'
    assert 'headers' not in files['.mcp.json'].decode() and 'command' not in files['.mcp.json'].decode()


def test_zip_is_reproducible_and_relative():
    files=p.assemble(inputs(),'a'*40,docs=True)
    first=p.zip_bytes(files);assert first==p.zip_bytes(dict(reversed(list(files.items()))))
    with zipfile.ZipFile(io.BytesIO(first)) as z:
        for name in z.namelist():
            assert name.startswith('mastermind-workforce/') and '..' not in name
            assert z.read(name)==files[name.removeprefix('mastermind-workforce/')]


def test_missing_existing_craft_refuses_instead_of_rebuilding():
    with pytest.raises(ValueError,match='PLUGIN_SKILL_MISSING'):p.assemble({},'a'*40)


def test_escaping_skill_path_refuses():
    data=inputs();data['skills/mastermind-worker-bootstrap/../../escape']=b'x'
    with pytest.raises(ValueError,match='PLUGIN_SOURCE_PATH_INVALID'):p.assemble(data,'a'*40)


def test_different_source_versions_do_not_reuse_native_plugin_version():
    first=json.loads(p.assemble(inputs(),'a'*40)['.codex-plugin/plugin.json'])
    second=json.loads(p.assemble(inputs(),'b'*40)['.codex-plugin/plugin.json'])
    assert first['version']!=second['version']
    assert 'aaaaaaaaaaaa' in first['version']


def test_skills_only_and_docs_variants_do_not_collide_in_native_cache():
    core=p.assemble(inputs(),'a'*40,docs=False)
    docs=p.assemble(inputs(),'a'*40,docs=True)
    cm=json.loads(core['.codex-plugin/plugin.json'])
    dm=json.loads(docs['.codex-plugin/plugin.json'])
    assert cm['name']==dm['name']=='mastermind-workforce'
    assert cm['version']!=dm['version']
    assert json.loads(core['BUILD.json'])['variant']=='skills-only'
    assert json.loads(docs['BUILD.json'])['variant']=='public-docs'



@pytest.mark.parametrize('missing', p.ORCHESTRATION_ROLE_FILES)
def test_incomplete_orchestration_role_closure_refuses(missing):
    data = inputs()
    del data['skills/mastermind-fabric-orchestration/'+missing]
    with pytest.raises(ValueError, match='PLUGIN_SKILL_MISSING'):
        p.assemble(data, 'a'*40)


def test_unreviewed_orchestration_role_asset_refuses_package():
    data = inputs()
    data['skills/mastermind-fabric-orchestration/scripts/unknown.py'] = b'print(1)'
    with pytest.raises(ValueError, match='PLUGIN_ROLE_CLOSURE_INVALID'):
        p.assemble(data, 'a'*40)


def test_source_collector_adds_roles_only_when_packaging_plugin(monkeypatch):
    roles = ['skills/mastermind-fabric-orchestration/'+name
             for name in p.ORCHESTRATION_ROLE_FILES]
    entries = sorted(source_install.EXACT_FILES) + [
        'skills/mastermind-worker-bootstrap/SKILL.md',
        'research/worker_craft/mastermind-craft/SKILL.md',
    ] + roles
    listing = b''.join(
        (b'100644 blob '+b'a'*40+b'\t'+name.encode()+b'\0')
        for name in entries
    )
    calls = []
    def git_read(command, **kwargs):
        calls.append(tuple(command))
        if 'ls-tree' in command:
            return listing
        assert command[-2] == 'show'
        return b'file:'+command[-1].encode()
    monkeypatch.setattr(source_install.subprocess, 'check_output', git_read)
    default = source_install.source_files('/fixture', 'a'*40)
    extended = source_install.source_files('/fixture', 'a'*40,
                                           include_orchestration=True)
    assert set(extended)-set(default) == set(roles)
    assert set(default).isdisjoint(roles)
    assert extended['skills/mastermind-fabric-orchestration/SKILL.md'].startswith(b'file:')
    for role in roles:
        assert role in extended
    with pytest.raises(ValueError, match='SOURCE_SELECTOR_INVALID'):
        source_install.source_files('/fixture', 'a'*40, include_orchestration='yes')
    assert calls


def test_generated_plugin_has_no_new_auth_or_mcp_grants():
    files = p.assemble(inputs(), 'b'*40)
    package = files['.codex-plugin/plugin.json']
    claude = files['.claude-plugin/plugin.json']
    assert set(json.loads(package)) == {'name', 'version', 'description', 'skills'}
    assert set(json.loads(claude)) == {'name', 'version', 'description', 'skills', 'author'}
    assert '.mcp.json' not in files
    assert b'mcpServers' not in package
    assert b'mcpServers' not in claude
    build = json.loads(files['BUILD.json'])
    assert build['execution_authority'] is False
    assert build['native_skill_attested'] is False
    assert build['source_state'] == 'SOURCE_CANDIDATE'

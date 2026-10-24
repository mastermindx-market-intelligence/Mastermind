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



def existing_workspace_manifest():
    """Existing live plugin schema, synthetic owner and no credentials."""
    return json.dumps({
        'name': 'mastermind-worker-bootstrap',
        'version': '0.2.0-candidate.ga865b48b9ac3',
        'skills': './skills/',
        'description': 'Existing Craft/Worker Bootstrap private package.',
        'author': {'name': 'Source Owner', 'email': 'example@example.invalid'},
        'interface': {
            'capabilities': ['Read'], 'category': 'Developer Tools',
            'displayName': 'Mastermind Workforce', 'developerName': 'Source Owner',
            'shortDescription': 'Worker roles',
            'longDescription': 'Worker startup, Craft roles and bounded outcomes.',
        },
    }, sort_keys=True).encode()


def test_existing_workspace_update_preserves_plugin_identity_and_grants():
    before = json.loads(existing_workspace_manifest())
    files = p.assemble_existing_workspace_update(
        inputs(), 'a'*40, current_manifest_bytes=existing_workspace_manifest())
    manifest = json.loads(files['.codex-plugin/plugin.json'])
    assert manifest['name'] == 'mastermind-worker-bootstrap'
    assert manifest['version'] == '0.2.1-candidate.gaaaaaaaaaaaa'
    assert {k:v for k,v in manifest.items() if k != 'version'} == {
        k:v for k,v in before.items() if k != 'version'}
    assert '.claude-plugin/plugin.json' not in files
    assert '.mcp.json' not in files
    build = json.loads(files['BUILD.json'])
    assert build['variant'] == 'existing-workspace-update'
    assert build['source_commit'] == 'a'*40
    assert build['existing_plugin_name'] == manifest['name']
    assert build['release_id_cas_required'] is True
    assert build['execution_authority'] is False
    for rel in p.ORCHESTRATION_ROLE_FILES:
        assert 'skills/mastermind-fabric-orchestration/'+rel in files
    zipped = p.zip_bytes(files, package_root=manifest['name'])
    with zipfile.ZipFile(io.BytesIO(zipped)) as archive:
        assert all(x.startswith('mastermind-worker-bootstrap/') for x in archive.namelist())
        assert archive.read('mastermind-worker-bootstrap/.codex-plugin/plugin.json') == files['.codex-plugin/plugin.json']
    assert zipped == p.zip_bytes(dict(reversed(list(files.items()))), package_root=manifest['name'])


@pytest.mark.parametrize('mutation', [
    {'name':'mastermind-workforce'},
    {'name':'mastermind-other'},
    {'skills':'../../unexpected'},
    {'mcpServers':'./.mcp.json'},
    {'hooks':'./hooks.json'},
    {'interface':{'capabilities':['Read','Write']}},
    {'interface':{'capabilities':['Write']}},
    {'interface':{'capabilities':['Read'], 'unexpected_grant':True}},
    {'author':None},
    {'version':'not-a-version'},
])
def test_workspace_update_refuses_wrong_identity_or_grants(mutation):
    source = json.loads(existing_workspace_manifest())
    source.update(mutation)
    with pytest.raises(ValueError, match='WORKSPACE_PLUGIN_'):
        p.assemble_existing_workspace_update(
            inputs(), 'a'*40, current_manifest_bytes=json.dumps(source).encode())


def test_workspace_manifest_source_cannot_add_unreviewed_extra_role():
    source=inputs()
    source['skills/mastermind-fabric-orchestration/scripts/rogue.py']=b'print(1)'
    with pytest.raises(ValueError, match='PLUGIN_ROLE_CLOSURE_INVALID'):
        p.assemble_existing_workspace_update(
            source,'a'*40,current_manifest_bytes=existing_workspace_manifest())




def test_workspace_manifest_reader_readback_and_no_follow(tmp_path):
    real = tmp_path/'current.json'
    real.write_bytes(existing_workspace_manifest())
    assert p.read_workspace_manifest_file(real) == existing_workspace_manifest()
    link = tmp_path/'alias.json'
    link.symlink_to(real)
    with pytest.raises(ValueError,match='WORKSPACE_MANIFEST_UNSAFE'):
        p.read_workspace_manifest_file(link)
    with pytest.raises(ValueError,match='WORKSPACE_MANIFEST_UNSAFE'):
        p.read_workspace_manifest_file(tmp_path/'missing.json')
    with pytest.raises(ValueError,match='WORKSPACE_MANIFEST_UNSAFE'):
        p.read_workspace_manifest_file(tmp_path)



def test_workspace_variant_rejects_malformed_source_manifest():
    for data in (b'', b'null', b'[]', b'notjson', b'{"name":1,"name":2}',
                 b'{"version":NaN}', b'{' + b'a' * 65537):
        with pytest.raises(ValueError, match='WORKSPACE_MANIFEST_INVALID|WORKSPACE_PLUGIN_'):
            p.assemble_existing_workspace_update(inputs(),'a'*40,current_manifest_bytes=data)



def test_workspace_update_requires_single_immutable_source_commit():
    with pytest.raises(ValueError, match='EXACT_SOURCE_COMMIT_REQUIRED'):
        p.assemble_existing_workspace_update(
            inputs(),'main',current_manifest_bytes=existing_workspace_manifest())

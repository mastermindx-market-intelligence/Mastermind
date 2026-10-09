import io
import json
import zipfile
import pytest
from ops.fabric_launch import plugin as p


def inputs():
    return {'research/worker_craft/mastermind-craft/SKILL.md':b'unchanged Craft',
            'research/worker_craft/mastermind-craft/references/reviewer.md':b'unchanged review',
            'skills/mastermind-worker-bootstrap/SKILL.md':b'boot',
            'ops/fabric_launch/context.py':b'not copied to plugin'}


def test_generated_distribution_preserves_single_source_bytes():
    files=p.assemble(inputs(),'a'*40)
    assert files['skills/mastermind-craft/SKILL.md']==b'unchanged Craft'
    assert files['skills/mastermind-craft/references/reviewer.md']==b'unchanged review'
    assert 'ops/fabric_launch/context.py' not in files
    build=json.loads(files['BUILD.json'])
    assert build['source_state']=='SOURCE_CANDIDATE'
    assert build['native_skill_attested'] is False and build['execution_authority'] is False
    assert build['mcp_servers']==[] and '.mcp.json' not in files


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

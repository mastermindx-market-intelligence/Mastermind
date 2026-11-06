"""Opt-in, credential-free native discovery; no model turns or live installation."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
FLAG = 'MASTERMIND_REAL_SPECIALIST_SKILLS_CATALOG_TEST'


@pytest.mark.skipif(os.environ.get(FLAG) != '1', reason='explicit credential-free Codex catalog opt-in required')
@pytest.mark.parametrize('include_native', [False, True])
def test_specialist_methods_discovered_and_cleared(tmp_path, capsys, include_native):
    # Reuse the existing tested client, protocol and identity owners.
    from control_plane.codex_operator_adapter import _CLIENT_INFO
    from scripts.ohf.laboratory import AppServerClient
    from scripts.ohf.protocol import (enabled_skill_names, extra_roots_set_params,
                                      parse_skills_list_strict, skills_list_params)
    from scripts.package_mastermind_specialists import SPECIALISTS, assemble, read_commit_files

    binary = shutil.which('codex')
    assert binary is not None, 'requested Codex binary unavailable'
    source_sha = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=ROOT, check=True,
                                capture_output=True, text=True, timeout=5).stdout.strip()
    artifact = assemble(read_commit_files(ROOT, source_sha, include_native), source_sha,
                        include_native_routing=include_native)
    assert '.mcp.json' not in artifact
    package = tmp_path / 'mastermind-specialists'
    workspace = tmp_path / 'workspace'
    home = tmp_path / 'isolated-home'
    workspace.mkdir(mode=0o700)
    home.mkdir(mode=0o700)
    for relative, data in artifact.items():
        destination = package / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
        assert destination.read_bytes() == data
    skills_root = (package / 'skills').resolve(strict=True)
    environment = {'PATH': os.environ.get('PATH', '/opt/homebrew/bin:/usr/bin:/bin'),
                   'HOME': str(home), 'CODEX_HOME': str(home), 'LC_ALL': 'C'}
    args = [binary, 'app-server', '--strict-config', '-c', 'sandbox_mode="read-only"',
            '-c', 'skills.bundled.enabled=false', '-c', 'features.plugins=false',
            '-c', 'features.apps=false', '-c', 'agents.enabled=false']
    client = AppServerClient(args, env=environment, cwd=workspace, start_new_session=True)
    names = []
    digests = {}
    try:
        client.start()
        initialized = client.request('initialize', {'clientInfo': _CLIENT_INFO,
                                      'capabilities': {'experimentalApi': True}}, timeout=10)
        client.notify('initialized', {})
        client.request('skills/extraRoots/set', extra_roots_set_params([]), timeout=10)
        def catalog():
            return parse_skills_list_strict(
                client.request('skills/list', skills_list_params(str(workspace)), timeout=10),
                expected_cwd=str(workspace))
        assert enabled_skill_names(catalog()) == []
        client.request('skills/extraRoots/set', extra_roots_set_params([str(skills_root)]), timeout=10)
        rows = catalog()
        expected = SPECIALISTS + (('agent-pools',) if include_native else ())
        names = sorted(enabled_skill_names(rows))
        assert names == sorted('mastermind-specialists:' + name for name in expected)
        for row in rows:
            if row.get('enabled') is not True:
                continue
            name = str(row['name']).removeprefix('mastermind-specialists:')
            assert name in expected
            path = (skills_root / name / 'SKILL.md').resolve(strict=True)
            assert row.get('path') == str(path)
            assert path.is_file() and not path.is_symlink()
            content = path.read_bytes()
            assert content == artifact[f'skills/{name}/SKILL.md']
            digests[name] = hashlib.sha256(content).hexdigest()
        client.request('skills/extraRoots/set', extra_roots_set_params([]), timeout=10)
        assert enabled_skill_names(catalog()) == []
        assert initialized.get('userAgent')
    finally:
        client.close()
        assert not client.alive()
    with capsys.disabled():
        print(json.dumps({'schema': 'mastermind.specialist_catalog_observation.v1',
                          'source_sha': source_sha, 'include_native_routing': include_native,
                          'provider_names': names, 'content_sha256': digests,
                          'candidate_only': True, 'installed': False, 'model_turns': 0,
                          'credential_home_isolated': True, 'clear_to_empty': True,
                          'process_closed': True}, sort_keys=True))

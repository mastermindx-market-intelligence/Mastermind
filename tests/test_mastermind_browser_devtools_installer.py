import json
import os
from pathlib import Path
import subprocess

import pytest

from integrations.mastermind_browser_devtools.installer import (
    RuntimeInstallError,
    install_devtools_runtime,
)


class FakeRunner:
    def __init__(self, *, npm_exit=0, version='1.10.1'):
        self.calls=[]
        self.npm_exit=npm_exit
        self.version=version

    def __call__(self, argv, **kwargs):
        self.calls.append((tuple(argv),dict(kwargs)))
        if 'ci' in argv:
            if self.npm_exit:
                raise subprocess.CalledProcessError(self.npm_exit,argv)
            prefix=Path(argv[argv.index('--prefix')+1])
            pkg=prefix/'node_modules/chrome-devtools-mcp'
            cli=pkg/'build/src/bin/chrome-devtools-mcp.js'
            cli.parent.mkdir(parents=True,exist_ok=True)
            (pkg/'package.json').write_text(json.dumps({
                'name':'chrome-devtools-mcp','version':'1.10.1'
            }))
            cli.write_text('console.log("fixture")\n')
            return subprocess.CompletedProcess(argv,0,'','')
        return subprocess.CompletedProcess(argv,0,self.version+'\n','')


def fixture(tmp_path):
    parent=tmp_path/'runtime-parent'
    cache=tmp_path/'cache'
    node=tmp_path/'bin/node'
    npm=tmp_path/'lib/npm-cli.js'
    node.parent.mkdir(parents=True)
    npm.parent.mkdir(parents=True)
    node.write_text('node fixture\n'); node.chmod(0o700)
    npm.write_text('npm fixture\n'); npm.chmod(0o600)
    return parent,cache,node,npm


def install(tmp_path, runner=None, **overrides):
    parent,cache,node,npm=fixture(tmp_path)
    kwargs=dict(
        runtime_parent=parent,
        cache_root=cache,
        node_executable=node,
        node_version='26.8.2',
        npm_cli=npm,
        run_command=runner or FakeRunner(),
    )
    kwargs.update(overrides)
    return kwargs, install_devtools_runtime(**kwargs)


def test_fresh_install_is_atomic_pinned_and_no_scripts(tmp_path):
    runner=FakeRunner()
    kwargs,result=install(tmp_path,runner)
    assert result.installed_now is True
    assert result.package_version=='1.10.1'
    assert result.final_root==kwargs['runtime_parent']/'chrome-devtools-mcp-1.10.1'
    assert result.cli_path==result.final_root/'node_modules/chrome-devtools-mcp/build/src/bin/chrome-devtools-mcp.js'
    assert result.is_admission is False
    assert result.final_root.is_dir()
    npm_call=runner.calls[0]
    assert npm_call[0][0]==str(kwargs['node_executable'])
    assert 'ci' in npm_call[0]
    assert '--ignore-scripts' in npm_call[0]
    assert '--no-audit' in npm_call[0]
    assert '--no-fund' in npm_call[0]
    assert '--prefix' in npm_call[0]
    assert npm_call[1]['shell'] is False
    assert set(npm_call[1]['env'])=={'HOME','LANG','LC_ALL','PATH'}
    assert npm_call[1]['env']['PATH']=='/usr/bin:/bin'
    assert len(list(kwargs['runtime_parent'].glob('.install-*')))==0


def test_second_install_is_idempotent_and_never_runs_npm_again(tmp_path):
    runner=FakeRunner()
    kwargs,first=install(tmp_path,runner)
    before=len(runner.calls)
    second=install_devtools_runtime(**kwargs)
    assert second.final_root==first.final_root
    assert second.installed_now is False
    new_calls=runner.calls[before:]
    assert len(new_calls)==1
    assert 'ci' not in new_calls[0][0]
    assert new_calls[0][0][-1]=='--version'


def test_existing_invalid_release_is_refused_not_replaced(tmp_path):
    parent,cache,node,npm=fixture(tmp_path)
    final=parent/'chrome-devtools-mcp-1.10.1'
    final.mkdir(parents=True)
    marker=final/'keep-me'
    marker.write_text('existing')
    runner=FakeRunner()
    with pytest.raises(RuntimeInstallError):
        install_devtools_runtime(
            runtime_parent=parent,cache_root=cache,node_executable=node,
            node_version='26.8.2',npm_cli=npm,run_command=runner)
    assert marker.read_text()=='existing'
    assert not runner.calls


@pytest.mark.parametrize('which',['runtime_parent','cache_root','node_executable','npm_cli'])
def test_symlinked_security_boundary_is_refused(tmp_path,which):
    parent,cache,node,npm=fixture(tmp_path)
    target=tmp_path/f'{which}-target'
    if which in {'runtime_parent','cache_root'}:
        target.mkdir()
    else:
        target.write_text('x'); target.chmod(0o700)
    link=tmp_path/f'{which}-link'
    link.symlink_to(target,target_is_directory=which in {'runtime_parent','cache_root'})
    kwargs=dict(runtime_parent=parent,cache_root=cache,node_executable=node,
                node_version='26.8.2',npm_cli=npm,run_command=FakeRunner())
    kwargs[which]=link
    with pytest.raises(RuntimeInstallError):
        install_devtools_runtime(**kwargs)


def test_npm_failure_leaves_no_final_or_staging_runtime(tmp_path):
    runner=FakeRunner(npm_exit=7)
    parent,cache,node,npm=fixture(tmp_path)
    with pytest.raises(RuntimeInstallError):
        install_devtools_runtime(
            runtime_parent=parent,cache_root=cache,node_executable=node,
            node_version='26.8.2',npm_cli=npm,run_command=runner)
    assert not (parent/'chrome-devtools-mcp-1.10.1').exists()
    assert not list(parent.glob('.install-*'))


def test_cli_version_mismatch_is_cleaned_before_publication(tmp_path):
    runner=FakeRunner(version='1.10.2')
    parent,cache,node,npm=fixture(tmp_path)
    with pytest.raises(RuntimeInstallError):
        install_devtools_runtime(
            runtime_parent=parent,cache_root=cache,node_executable=node,
            node_version='26.8.2',npm_cli=npm,run_command=runner)
    assert not (parent/'chrome-devtools-mcp-1.10.1').exists()
    assert not list(parent.glob('.install-*'))


def test_runtime_inputs_require_real_node_and_npm_files(tmp_path):
    parent,cache,node,npm=fixture(tmp_path)
    node.unlink()
    with pytest.raises(RuntimeInstallError):
        install_devtools_runtime(
            runtime_parent=parent,cache_root=cache,node_executable=node,
            node_version='26.8.2',npm_cli=npm,run_command=FakeRunner())


def test_committed_manifest_drift_refuses_before_npm(tmp_path):
    runner=FakeRunner()
    package_root=tmp_path/'package'
    package_root.mkdir()
    source=Path(__file__).resolve().parents[1]/'integrations/mastermind_browser_devtools_runtime'
    (package_root/'package.json').write_text((source/'package.json').read_text().replace('1.10.1','1.10.2'))
    (package_root/'package-lock.json').write_text((source/'package-lock.json').read_text())
    parent,cache,node,npm=fixture(tmp_path)
    with pytest.raises(RuntimeInstallError):
        install_devtools_runtime(
            runtime_parent=parent,cache_root=cache,node_executable=node,
            node_version='26.8.2',npm_cli=npm,package_root=package_root,
            run_command=runner)
    assert not runner.calls

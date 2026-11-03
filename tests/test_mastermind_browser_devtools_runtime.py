import json
from pathlib import Path
import pytest

from integrations.mastermind_browser_devtools.runtime import (
    CLI_RELATIVE_PATH,
    PACKAGE_INTEGRITY,
    PACKAGE_NAME,
    PACKAGE_RESOLVED,
    PACKAGE_VERSION,
    RuntimePackageError,
    build_runtime_install_plan,
    validate_runtime_package,
)

ROOT=Path(__file__).resolve().parents[1]
PACKAGE_ROOT=ROOT/'integrations/mastermind_browser_devtools_runtime'


def load_json(name):
    return json.loads((PACKAGE_ROOT/name).read_text())


def test_committed_runtime_package_is_exact_and_valid():
    package=load_json('package.json')
    lock=load_json('package-lock.json')
    identity=validate_runtime_package(package,lock)
    assert identity.package_name==PACKAGE_NAME=='chrome-devtools-mcp'
    assert identity.package_version==PACKAGE_VERSION=='1.10.1'
    assert identity.integrity==PACKAGE_INTEGRITY
    assert identity.resolved==PACKAGE_RESOLVED
    assert identity.cli_relative_path==CLI_RELATIVE_PATH
    assert identity.is_installation is False
    assert package=={
        'name':'mastermind-browser-devtools-runtime',
        'private':True,
        'version':'0.1.0',
        'dependencies':{'chrome-devtools-mcp':'1.10.1'},
    }


@pytest.mark.parametrize('mutation',[
    lambda p,l: p['dependencies'].__setitem__('chrome-devtools-mcp','^1.10.1'),
    lambda p,l: p['dependencies'].__setitem__('left-pad','1.3.0'),
    lambda p,l: l.__setitem__('lockfileVersion',2),
    lambda p,l: l['packages']['node_modules/chrome-devtools-mcp'].__setitem__('version','1.10.2'),
    lambda p,l: l['packages']['node_modules/chrome-devtools-mcp'].__setitem__('integrity','sha512-wrong'),
    lambda p,l: l['packages']['node_modules/chrome-devtools-mcp'].__setitem__('resolved','https://example.com/x.tgz'),
])
def test_runtime_package_validation_fails_closed_on_drift(mutation):
    package=load_json('package.json')
    lock=load_json('package-lock.json')
    mutation(package,lock)
    with pytest.raises(RuntimePackageError):
        validate_runtime_package(package,lock)


@pytest.mark.parametrize('version',[
    '20.19.0','20.99.1','22.12.0','22.20.0','23.0.0','26.8.2'
])
def test_install_plan_accepts_package_supported_node_versions(version):
    plan=build_runtime_install_plan(
        runtime_root='/Volumes/Mastermind/mastermind-browser-devtools/runtime',
        cache_root='/Volumes/Mastermind/mastermind-browser-devtools/npm-cache',
        node_executable='/opt/mmx/node/bin/node',
        node_version=version,
        npm_cli='/opt/mmx/node/lib/node_modules/npm/bin/npm-cli.js',
    )
    assert plan.command=='/opt/mmx/node/bin/node'
    assert plan.node_version==version
    assert plan.cli_path.endswith('/'+CLI_RELATIVE_PATH)
    assert plan.argv==(
        '/opt/mmx/node/lib/node_modules/npm/bin/npm-cli.js',
        'ci',
        '--prefix','/Volumes/Mastermind/mastermind-browser-devtools/runtime',
        '--cache','/Volumes/Mastermind/mastermind-browser-devtools/npm-cache',
        '--ignore-scripts','--no-audit','--no-fund',
    )
    assert plan.package_version=='1.10.1'
    assert plan.is_installation is False


@pytest.mark.parametrize('version',['19.99.0','20.18.9','21.9.9','22.11.9','bad','26'])
def test_install_plan_refuses_unsupported_or_malformed_node_versions(version):
    with pytest.raises(RuntimePackageError):
        build_runtime_install_plan(
            runtime_root='/Volumes/Mastermind/mastermind-browser-devtools/runtime',
            cache_root='/Volumes/Mastermind/mastermind-browser-devtools/npm-cache',
            node_executable='/opt/mmx/node/bin/node',
            node_version=version,
            npm_cli='/opt/mmx/node/lib/node_modules/npm/bin/npm-cli.js',
        )


@pytest.mark.parametrize('field,value',[
    ('runtime_root','relative/runtime'),
    ('runtime_root','/tmp/../runtime'),
    ('runtime_root','/'),
    ('cache_root','cache'),
    ('cache_root','/tmp/../cache'),
    ('node_executable','node'),
    ('node_executable','/tmp/../node'),
    ('npm_cli','npm'),
    ('npm_cli','/tmp/../npm'),
])
def test_install_plan_requires_absolute_normalized_controller_paths(field,value):
    kwargs=dict(
        runtime_root='/Volumes/Mastermind/mastermind-browser-devtools/runtime',
        cache_root='/Volumes/Mastermind/mastermind-browser-devtools/npm-cache',
        node_executable='/opt/mmx/node/bin/node',
        node_version='26.8.2',
        npm_cli='/opt/mmx/node/lib/node_modules/npm/bin/npm-cli.js',
    )
    kwargs[field]=value
    with pytest.raises(RuntimePackageError):
        build_runtime_install_plan(**kwargs)


def test_install_plan_has_no_registry_override_script_execution_or_shell():
    plan=build_runtime_install_plan(
        runtime_root='/Volumes/Mastermind/mastermind-browser-devtools/runtime',
        cache_root='/Volumes/Mastermind/mastermind-browser-devtools/npm-cache',
        node_executable='/opt/mmx/node/bin/node',
        node_version='26.8.2',
        npm_cli='/opt/mmx/node/lib/node_modules/npm/bin/npm-cli.js',
    )
    rendered=' '.join((plan.command,*plan.argv))
    assert '--ignore-scripts' in rendered
    assert ' npm install ' not in ' '+rendered+' '
    assert '--registry' not in rendered
    assert 'sh -c' not in rendered
    assert 'bash -c' not in rendered

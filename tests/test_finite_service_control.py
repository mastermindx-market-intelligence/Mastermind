"""Execute disposable controller copies; no live root or service effect."""
from pathlib import Path
import pytest
from test_executive_service_control import _run

SHA='a'*40
MANIFEST='b'*64
ARGS=('--expected-sha',SHA,'--expected-manifest-sha256',MANIFEST)


def prepare(tmp_path, *, installed=True):
    def change(script):
        text=script.read_text()
        release=tmp_path/'releases'/SHA/'ops/executive_os'
        text=text.replace('MCP_RELEASE_ROOT="/Library/Application Support/MastermindExecutive/releases"',
                          'MCP_RELEASE_ROOT="'+str(tmp_path/'releases')+'"')
        if installed:
            source=('SCRIPT_SOURCE="${BASH_SOURCE[0]}"\n'
                    'SCRIPT_DIR="$(builtin cd -P "$(/usr/bin/dirname "$SCRIPT_SOURCE")" && /bin/pwd)"\n'
                    'SCRIPT_PATH="$SCRIPT_DIR/$(/usr/bin/basename "$SCRIPT_SOURCE")"')
            replacement=(f'SCRIPT_SOURCE="{release}/service-control.sh"\n'
                         f'SCRIPT_DIR="{release}"\nSCRIPT_PATH="{release}/service-control.sh"')
            assert source in text
            text=text.replace(source,replacement)
        script.write_text(text)
        shim=tmp_path/'native-shims/gateway-preflight-python'
        shim.write_text('#!/bin/bash\n'
            '[ "$#" -eq 9 ] || exit 97\n'
            '[ "$1" = "-I" ] && [ "$2" = "-S" ] && [ "$3" = "-B" ] || exit 97\n'
            f'[ "$4" = "{release}/finite_service_lifecycle.py" ] || exit 97\n'
            '[ "$6" = "--expected-sha" ] && [ "$8" = "--expected-manifest-sha256" ] || exit 97\n'
            f'[ "$7" = "{SHA}" ] && [ "$9" = "{MANIFEST}" ] || exit 97\n'
            'printf "bounded-helper:%s\\n" "$5"\n')
        shim.chmod(0o755)
    return change


@pytest.mark.parametrize('action',['start-finite','stop-finite','status-finite'])
def test_fixed_finite_action_passes_isolated_exact_release_bindings(tmp_path,action):
    code,out,err,launches,*_= _run(tmp_path,action,[],extra_args=ARGS,prepare=prepare(tmp_path))
    assert code==0,(out,err)
    assert out.strip()=='bounded-helper:'+action and launches==[]


@pytest.mark.parametrize('args',[(),('--expected-sha',SHA),ARGS+('--label','com.other'),
    ('--expected-sha','x'*40,'--expected-manifest-sha256',MANIFEST),
    ('--expected-sha',SHA,'--expected-manifest-sha256',MANIFEST+'\n')])
def test_invalid_or_extended_arguments_never_invoke_helper(tmp_path,args):
    code,out,err,launches,*_= _run(tmp_path,'start-finite',[],extra_args=args,prepare=prepare(tmp_path))
    assert code==64 and 'bounded-helper' not in out and launches==[]


@pytest.mark.parametrize('installed,uid,os_name,expected',[
    (False,'0','Darwin',65),(True,'501','Darwin',77),(True,'0','Linux',69)])
def test_finite_lifecycle_requires_actual_installed_source_and_root_darwin(tmp_path,installed,uid,os_name,expected):
    code,out,err,launches,*_=_run(tmp_path,'start-finite',[],extra_args=ARGS,
        prepare=prepare(tmp_path,installed=installed),fake_uid=uid,fake_os=os_name)
    assert code==expected and 'bounded-helper' not in out and launches==[]


def test_forged_installed_argv_zero_does_not_qualify_checkout_source(tmp_path):
    code,out,err,launches,*_=_run(tmp_path,'start-finite',[],extra_args=ARGS,
        prepare=prepare(tmp_path,installed=False),
        spoof_argv0=str(tmp_path/'releases'/SHA/'ops/executive_os/service-control.sh'))
    assert code==65 and 'bounded-helper' not in out and launches==[]

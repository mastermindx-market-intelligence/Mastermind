"""Pre-launch fixture selection only; never run the real provider journey here."""
import os
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET

import pytest

from tests import test_paid_provider_entry_linux as fixture


@pytest.mark.parametrize('platform,version,flag,expected',[
    ('linux',(3,12),None,False),('linux',(3,12),'',False),
    ('linux',(3,12),'0',False),('linux',(3,12),'true',False),
    ('linux',(3,12),'01',False),('linux',(3,12),'1',True),
    ('linux',(3,11),'1',False),('darwin',(3,12),'1',False),
])
def test_controlled_fixture_request_is_exact_and_platform_specific(monkeypatch,platform,version,flag,expected):
    with monkeypatch.context() as model:
        model.setattr(fixture.sys,'platform',platform)
        model.setattr(fixture.sys,'version_info',version)
        if flag is None:model.delenv('MMX_H1_CONTROLLED_LINUX_FIXTURE',raising=False)
        else:model.setenv('MMX_H1_CONTROLLED_LINUX_FIXTURE',flag)
        observed=fixture._controlled_linux_fixture_requested()
    assert observed is expected


def test_generic_host_skips_all_five_before_source_or_namespace_effects(tmp_path):
    marker=tmp_path/'must-not-start';plugin=tmp_path/'controlled_fixture_trap.py'
    plugin.write_text('from pathlib import Path\n'
        'def pytest_collection_modifyitems(items):\n'
        ' def forbidden(*args,**kwargs):\n'
        '  Path('+repr(str(marker))+').write_bytes(b"started")\n'
        '  raise AssertionError("generic host started controlled fixture")\n'
        ' for item in items:\n'
        '  item.obj.__globals__["_source_stage"]=forbidden\n')
    report=tmp_path/'generic-host.xml'
    env={**os.environ,'PYTEST_DISABLE_PLUGIN_AUTOLOAD':'1','PYTHONDONTWRITEBYTECODE':'1',
         'PYTHONPATH':str(tmp_path)+os.pathsep+str(Path(__file__).resolve().parents[1])}
    env.pop('MMX_H1_CONTROLLED_LINUX_FIXTURE',None)
    child=subprocess.run([sys.executable,'-m','pytest','-q','--noconftest',
        '-p','no:cacheprovider','-p','controlled_fixture_trap','--junitxml='+str(report),
        'tests/test_paid_provider_entry_linux.py::test_actual_compiled_c_executor_model_and_original_result'],
        cwd=Path(__file__).resolve().parents[1],env=env,
        stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=30)
    assert child.returncode==0 and not marker.exists()
    suite=ET.parse(report).getroot().find('testsuite')
    assert {key:suite.get(key)for key in ('tests','skipped','failures','errors')}==dict(
        tests='5',skipped='5',failures='0',errors='0')

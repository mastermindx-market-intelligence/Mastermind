"""Exact new dependency closure; no installed sources, hosts or Broker state."""
import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shutil
import subprocess

import pytest

SOURCE = Path(__file__).resolve().parents[1] / 'integrations/session_bridge/native_broker_admission'


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


@pytest.fixture
def closure(tmp_path):
    pins = json.loads((SOURCE/'SUPPORT_CLOSURE.json').read_text())['files']
    for name, pin in pins.items():
        raw = (SOURCE/'fixtures'/(name+'.base')).read_bytes()
        assert digest(raw) == pin['pre_sha256']
        (tmp_path/name).write_bytes(raw)
        assert digest((SOURCE/(name+'.patch')).read_bytes()) == pin['patch_sha256']
        subprocess.run(['git','apply','--unidiff-zero',str(SOURCE/(name+'.patch'))],cwd=tmp_path,check=True)
        assert digest((tmp_path/name).read_bytes()) == pin['candidate_sha256']
    return tmp_path, module(tmp_path/'support_bundle.py', 'new_native_support')


def test_copy_manifest_and_publisher_have_same_complete_dependency_set(closure):
    path, publisher = closure
    shell = (path/'remote_sub.sh').read_text()
    match = re.search(r'^SUPPORT_FILES=\((.*?)\n\)',shell,re.M|re.S)
    assert match is not None
    assert frozenset(match.group(1).split()) == publisher.SOURCE_FILES
    assert {'lease_broker.py','native_broker_admission.py'} <= publisher.SOURCE_FILES


def test_historical_immutable_generations_are_unchanged(closure, tmp_path):
    _, publisher = closure
    old = tmp_path/'old_support.py'
    shutil.copyfile(SOURCE/'fixtures/support_bundle.py.base',old)
    before = module(old, 'old_native_support')
    assert publisher.SOURCE_GENERATIONS[1:] == before.SOURCE_GENERATIONS
    assert publisher.SOURCE_FILES == before.SOURCE_FILES | {'native_broker_admission.py'}
    assert publisher._EXT_SYMLINKS == before._EXT_SYMLINKS
    assert publisher._ROOT_SYMLINKS == before._ROOT_SYMLINKS


def test_new_generation_cannot_publish_without_native_dependency(closure,tmp_path):
    _, publisher = closure
    source = tmp_path/'source'; source.mkdir()
    stable = tmp_path/'stable'; stable.mkdir()
    manifest = {}
    for name in publisher.SOURCE_FILES:
        payload = (name+'\n').encode(); manifest[name] = digest(payload)
        if name != 'native_broker_admission.py': (source/name).write_bytes(payload)
    with pytest.raises((ValueError,FileNotFoundError)):
        publisher.publish(source,stable,manifest)
    assert not (stable.parent/'support-releases'/digest(publisher._canon_manifest(manifest))).exists()


def test_publisher_change_only_extends_closed_generations(closure,tmp_path):
    path, _ = closure
    before = ast.parse((SOURCE/'fixtures/support_bundle.py.base').read_text())
    after = ast.parse((path/'support_bundle.py').read_text())
    def functions(tree):
        return {node.name:ast.dump(node,include_attributes=False) for node in tree.body
                if isinstance(node,(ast.FunctionDef,ast.ClassDef))}
    assert functions(before) == functions(after)

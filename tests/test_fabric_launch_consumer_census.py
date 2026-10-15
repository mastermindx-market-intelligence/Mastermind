"""Regression controls for the independent install review's fail-open finding."""
import json
from pathlib import Path
import pytest
from ops.fabric_launch import install

WRAPPER=b'#!/bin/bash\ncase "$CMD" in\n*) exit 2;;\nesac\n'


@pytest.fixture
def scene(tmp_path, monkeypatch):
    wrapper=tmp_path/'pool';wrapper.write_bytes(WRAPPER)
    root=tmp_path/'studio';root.mkdir()
    monkeypatch.setattr(install,'STUDIO_CONSUMER_ROOT',root)
    return wrapper,root


def assert_no_swap(wrapper):
    with pytest.raises(ValueError):
        install.activate(wrapper,Path('/release'),install.sha(WRAPPER))
    assert wrapper.read_bytes()==WRAPPER
    assert not list(wrapper.parent.glob('pool.pre-worker-bootstrap-*'))


def test_missing_root_is_unknown_not_zero_consumers(scene, monkeypatch):
    wrapper,root=scene;root.rmdir()
    assert_no_swap(wrapper)


def test_non_directory_root_refuses(scene):
    wrapper,root=scene;root.rmdir();root.write_text('not directory')
    assert_no_swap(wrapper)


def test_unlistable_root_refuses(scene, monkeypatch):
    wrapper,root=scene;original=install.os.scandir
    def denied(path):
        if str(path)==str(root):raise PermissionError('fixture')
        return original(path)
    monkeypatch.setattr(install.os,'scandir',denied)
    assert_no_swap(wrapper)


@pytest.mark.parametrize('body',[b'[]',b'null',b'"not config"',b'{"fleetStatus":null}',b'{"fleetStatus":[]}'])
def test_non_object_configuration_refuses(scene, body):
    wrapper,root=scene;account=root/'account';account.mkdir();(account/'config.json').write_bytes(body)
    assert_no_swap(wrapper)


def test_partial_account_directory_does_not_disappear_from_census(scene):
    wrapper,root=scene;(root/'account-under-upgrade').mkdir()
    assert_no_swap(wrapper)


def test_symlink_account_refuses(scene, tmp_path):
    wrapper,root=scene;outside=tmp_path/'outside';outside.mkdir();(outside/'config.json').write_text('{}')
    (root/'account').symlink_to(outside,target_is_directory=True)
    assert_no_swap(wrapper)


@pytest.mark.parametrize('value',['true',1,None])
def test_malformed_enabled_flag_cannot_suppress_a_pin(scene, value):
    wrapper,root=scene;account=root/'account';account.mkdir()
    (account/'config.json').write_text(json.dumps({'fleetStatus':{'enabled':value,'fabricLauncherPath':str(wrapper),'fabricLauncherSha256':install.sha(WRAPPER)}}))
    assert_no_swap(wrapper)


def test_duplicate_keys_refuse_instead_of_last_value_wins(scene):
    wrapper,root=scene;account=root/'account';account.mkdir()
    body='{"fleetStatus":{"enabled":true,"enabled":false,"fabricLauncherPath":'+json.dumps(str(wrapper))+',"fabricLauncherSha256":'+json.dumps(install.sha(WRAPPER))+'}}'
    (account/'config.json').write_text(body)
    assert_no_swap(wrapper)


def test_equivalent_launcher_path_remains_a_pinned_consumer(scene):
    wrapper,root=scene;(wrapper.parent/'alias-dir').mkdir();account=root/'account';account.mkdir()
    path=str(wrapper.parent/'alias-dir'/'..'/'pool')
    (account/'config.json').write_text(json.dumps({'fleetStatus':{'enabled':True,'fabricLauncherPath':path,'fabricLauncherSha256':install.sha(WRAPPER)}}))
    assert_no_swap(wrapper)


def test_candidate_census_failure_precedes_output_creation(scene, tmp_path):
    wrapper,root=scene;root.rmdir();out=tmp_path/'candidate'
    with pytest.raises(ValueError):
        install.stage_wrapper_candidate(wrapper,Path('/release'),install.sha(WRAPPER),out)
    assert not out.exists()
    assert wrapper.read_bytes()==WRAPPER


def test_empty_readable_registry_is_distinct_from_unavailable_registry(scene):
    wrapper,root=scene
    assert install.pinned_consumers(wrapper,'a'*64)==[]


def test_new_pin_during_preparation_blocks_the_final_swap(scene, monkeypatch):
    wrapper,root=scene
    original_run=install.subprocess.run
    def syntax_and_new_pin(argv,**kwargs):
        result=original_run(argv,**kwargs)
        account=root/'concurrent-consumer';account.mkdir()
        (account/'config.json').write_text(json.dumps({'fleetStatus':{'enabled':True,'fabricLauncherPath':str(wrapper),'fabricLauncherSha256':install.sha(WRAPPER)}}))
        return result
    monkeypatch.setattr(install.subprocess,'run',syntax_and_new_pin)
    with pytest.raises(ValueError,match='PINNED_CONSUMER_RELEASE_REQUIRED'):
        install.activate(wrapper,Path('/release'),install.sha(WRAPPER))
    assert wrapper.read_bytes()==WRAPPER
    assert not list(wrapper.parent.glob('.pool-worker-bootstrap-*'))


def test_hardlinked_config_is_not_accepted_as_owned_evidence(scene, tmp_path):
    import os
    wrapper,root=scene;account=root/'account';account.mkdir()
    src=tmp_path/'source-config';src.write_text('{}')
    os.link(src,account/'config.json')
    assert_no_swap(wrapper)


def test_unbounded_registry_refuses_before_wrapper_write(scene):
    wrapper,root=scene
    for index in range(33):
        account=root/str(index);account.mkdir();(account/'config.json').write_text('{}')
    assert_no_swap(wrapper)

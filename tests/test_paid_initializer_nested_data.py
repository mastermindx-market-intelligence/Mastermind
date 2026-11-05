"""Explicit new source semantics and context DATA, never hook execution."""
import ast
import hashlib
import json
import os
from pathlib import Path
import sys

import pytest

from ops.native_fabric.quota_continuity.candidate import paid_initializer_nested_data as nested
from ops.native_fabric.quota_continuity.candidate import paid_initializer_token_data as token


def test_exact_original_and_explicit_transformation_only():
    original = nested._ORIGINAL
    assert len(original) == 587
    assert hashlib.sha256(original).hexdigest() == nested.LEGACY_SHA256
    before_last = original[:-len(nested._LAST)]
    assert b"GLM_SHIM_TOKEN" not in before_last
    assert b"BASH_SOURCE" not in original
    transformed = nested.transform_outer(original, contract=nested.CONTRACT)
    assert transformed == before_last+nested._REPLACEMENT
    assert b".host_glm_token.sh" not in transformed
    assert hashlib.sha256(transformed).hexdigest() == nested.TRANSFORMED_SHA256
    assert b"export GLM_SHIM_URL=http://127.0.0.1:4141" in transformed


@pytest.mark.parametrize("outer,contract", [
    (nested._ORIGINAL, "paid-host-env-held-fd.v1"),
    (nested._ORIGINAL, None), (bytearray(nested._ORIGINAL),nested.CONTRACT),
    (nested._ORIGINAL+b"\n",nested.CONTRACT),
    (nested._ORIGINAL.replace(b"4141",b"4142"),nested.CONTRACT),
    (nested._ORIGINAL.replace(b".host_glm_token.sh",b".other-helper.sh"),nested.CONTRACT),
])
def test_old_contract_and_outer_drift_refuse(outer, contract):
    with pytest.raises(nested.NestedDataRefused) as caught:
        nested.transform_outer(outer, contract=contract)
    assert str(caught.value) == "paid_nested_data_refused"


@pytest.fixture
def context(tmp_path):
    home=tmp_path/"inert-home"; lane=home/"lanes"
    system=tmp_path/"inert-system";system.mkdir()
    image=system/"python3";image.write_bytes(b"INERT NOT EXECUTED");image.chmod(0o700)
    return dict(environment={"HOME":str(home),"PATH":str(system)},
                expected_home=str(home),expected_glm_config=str(home/".glm/config.json"),
                expected_python=str(image),lane_root=str(lane),contract=nested.CONTRACT)


def test_effective_default_and_explicit_selector_without_overrides(context):
    original=dict(context["environment"])
    result=nested.bind_effective_context(**context)
    assert set(result)=={"schema_version","home","glm_config","python_path"}
    assert result["glm_config"]==context["expected_glm_config"]
    assert context["environment"]==original and "GLM_CONFIG" not in original
    context["environment"]["GLM_CONFIG"]=context["expected_glm_config"]
    assert nested.bind_effective_context(**context)==result


@pytest.mark.parametrize("field,value", [
    ("HOME","/different"),("GLM_CONFIG","/different/config.json"),
    ("GLM_CONFIG",True),("GLM_CONFIG","relative/config.json"),
    ("PATH",True),("PATH","bad\0path"),
])
def test_context_drift_never_repaired(context, field, value):
    context["environment"][field]=value
    with pytest.raises(nested.NestedDataRefused):nested.bind_effective_context(**context)
    assert context["environment"][field]==value


def test_actual_preempting_lane_python_refuses_system_relabel(context):
    preferred=Path(context["lane_root"])/"venv/bin";preferred.mkdir(parents=True)
    image=preferred/"python3";image.write_bytes(b"INERT");image.chmod(0o700)
    with pytest.raises(nested.NestedDataRefused):nested.bind_effective_context(**context)
    context["expected_python"]=str(image)
    assert nested.bind_effective_context(**context)["python_path"]==str(image)


def test_312_image_cannot_be_relabelled_python3_selector(context):
    context["expected_python"] += ".12"
    with pytest.raises(nested.NestedDataRefused):nested.bind_effective_context(**context)


def test_context_old_contract_and_lane_repoint_refuse(context):
    context["contract"]="paid-host-env-held-fd.v1"
    with pytest.raises(nested.NestedDataRefused):nested.bind_effective_context(**context)
    context["contract"]=nested.CONTRACT;context["lane_root"]+="-foreign"
    with pytest.raises(nested.NestedDataRefused):nested.bind_effective_context(**context)


@pytest.mark.parametrize("helper", [None, {}, object()])
def test_unqualified_helper_never_reaches_snapshot(monkeypatch, helper):
    calls=[]
    def forbidden(*a,**kw):calls.append(True);raise AssertionError("snapshot reached")
    monkeypatch.setattr(nested,"sealed_snapshot",forbidden)
    with pytest.raises(nested.NestedDataRefused):
        with nested.prepare_nested_inputs(nested._ORIGINAL,helper,contract=nested.CONTRACT):
            pytest.fail("unqualified helper yielded")
    assert not calls


def test_no_module_executes_hook_shell_or_process():
    for module in (nested, token):
        tree=ast.parse(Path(module.__file__).read_bytes())
        calls=[n for n in ast.walk(tree)if isinstance(n,ast.Call)]
        assert not any(isinstance(n.func,ast.Name)and n.func.id in {"eval","exec","compile"}
                       for n in calls)
        assert not any(isinstance(n.func,ast.Attribute)and n.func.attr in
                       {"system","Popen","run","execve","spawn"}for n in calls)


@pytest.mark.skipif(sys.platform!="linux"or not hasattr(os,"memfd_create"),
                    reason="real Linux sealed helper and outer inputs required")
def test_actual_private_data_to_sealed_outer_and_context(tmp_path,context):
    raw=b'export GLM_SHIM_TOKEN="'+b"a"*32+b'"\n'
    path=tmp_path/"synthetic-helper";path.write_bytes(raw);path.chmod(0o600)
    info=path.stat()
    if not info.st_uid or not info.st_gid:pytest.skip("positive-account profile fixture")
    expected=dict(sha256=hashlib.sha256(raw).hexdigest(),size=len(raw),
                  uid=info.st_uid,gid=info.st_gid,mode=0o600)
    fd=os.open(path,os.O_RDONLY)
    try:
        with token.freeze_helper_data(fd,expected=expected)as helper:
            with nested.prepare_nested_inputs(nested._ORIGINAL,helper,contract=nested.CONTRACT)as prepared:
                outer=prepared.outer_fd
                assert os.pread(outer,65536,0)==nested._TRANSFORMED
                witness=prepared.witness
                assert set(witness)=={"schema_version","initialization_contract",
                    "legacy_outer_sha256","transformed_outer_sha256","helper"}
                assert b"a"*32 not in json.dumps(witness).encode()
                env=prepared.private_environment(context["environment"])
                prepared.check_environment(env)
                assert nested.bind_effective_context(**(context|{"environment":env}))["python_path"]==context["expected_python"]
                missing=dict(context["environment"])
                with pytest.raises(nested.NestedDataRefused):prepared.check_environment(missing)
                changed=dict(missing,GLM_SHIM_TOKEN="b"*32)
                with pytest.raises(nested.NestedDataRefused):prepared.check_environment(changed)
            with pytest.raises(OSError):os.fstat(outer)
            helper.check()
            with pytest.raises(nested.NestedDataRefused):prepared.check()
    finally:os.close(fd)

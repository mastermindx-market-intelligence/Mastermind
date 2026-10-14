"""Compiler/source binding regressions; no provider or host effects."""
import asyncio
import dataclasses
import hashlib
import json
import pytest
from test_attended_worker_definition import inputs
from test_attended_owner_assembly import fixed, compose
from test_fabric_attended_backend import harness
from test_fabric_owned_start_assembly import world, lr
from test_fabric_attended_claude import _prepare, _spec
from ops.executive_os import attended_worker_definition as render
from control_plane import fabric_attended_claude as compiler


def test_renderer_derives_digests_from_canonical_sources(inputs):
    args={k:v for k,v in inputs.items() if k not in ('service_source_sha256','permission_profile_sha256')}
    output=render.build_finite_worker_artifacts(**args)
    binding=json.loads(output['bindings.json'])['bindings'][0]
    assert binding['service_source_sha256']==inputs['release_manifest_sha256']
    assert binding['permission_profile_sha256']==compiler.finite_read_permission_digest()


@pytest.mark.parametrize('field',['service_source_sha256','permission_profile_sha256'])
def test_renderer_refuses_arbitrary_digest(inputs,field):
    args={k:v for k,v in inputs.items() if k not in ('service_source_sha256','permission_profile_sha256')}
    with pytest.raises(render.AttendedDefinitionError):
        render.build_finite_worker_artifacts(**{**args,field:'0'*64})


def test_actual_read_assignments_compile_expected_permission_digest():
    first=_prepare()
    second=_prepare(spec=_spec(prompt='Different useful READ assignment',run_id='other-run'))
    assert first.stdin_text!=second.stdin_text and first.run_id!=second.run_id
    assert first.settings_sha256==second.settings_sha256==compiler.finite_read_permission_digest()
    assert compiler.compiled_permission_digest(first)==first.settings_sha256


def test_service_binding_must_match_verified_entry_manifest(fixed):
    fixed.physical=dataclasses.replace(fixed.physical,service_source_sha256='0'*64)
    with pytest.raises(Exception,match='Fixed attended resources'):
        compose(fixed)


@pytest.mark.parametrize('drift',['digest','argv'])
def test_permission_drift_refuses_before_slot_lease_or_start(harness,drift):
    h=harness
    if drift=='digest':
        h.world.descriptor.settings_sha256='0'*64
    else:
        argv=list(h.world.descriptor.argv)
        argv[argv.index('--settings')+1]='{"permissions":{"allow":["Bash(*)"]}}'
        h.world.descriptor.argv=tuple(argv)
    with pytest.raises(Exception):
        asyncio.run(h.start())
    assert not h.slot.claimed and not h.inputs.log_path.exists()
    assert h.acquisitions==h.calls==h.credential_verifications==[]

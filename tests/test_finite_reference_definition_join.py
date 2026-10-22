"""Pure candidate bytes through real renderers; no production identity or files."""
import hashlib
import json

import pytest

from control_plane.executive_fabric_bridge_broker import BridgeConfig
from control_plane.executive_fabric_composition import _bindings
from control_plane.fabric_attended_routing import FINITE_DEFINITION_DIR, FINITE_SOCKET_PATH
from ops.executive_os import attended_worker_definition as render
from ops.executive_os import finite_reference_assignment as refs
from tests.test_attended_worker_definition import inputs


@pytest.fixture
def initial_definition(inputs, monkeypatch):
    # Synthetic coordinates only; never call the production randomness source.
    values = iter(('1' * 64, '2' * 64, '3' * 64))
    monkeypatch.setattr(refs, '_new_reference', lambda prefix: prefix + '-' + next(values))
    stanza = refs.prepare_finite_reference_stanza(registration_source={
        'release_commit': '1' * 40, 'previous_release_commit': '2' * 40,
        'material_source_digest': '3' * 64, 'export_sha256': '4' * 64,
    }, realm_generation=1)
    return stanza, {**inputs, 'worker_id': 'minimax-finite-01',
        'worker_user': '_mastermind_minimax', 'worker_group': '_mastermind_minimax',
        'worker_uid': 470, 'worker_gid': 470,
        'definition_dir': FINITE_DEFINITION_DIR, 'socket_path': FINITE_SOCKET_PATH,
        'host_ref': stanza['host_ref'], 'capacity_capability_id': 'cap.fixture',
        'native_capacity_enrollment': stanza}


def test_constructor_bytes_reach_real_worker_bridge_binding_and_control(initial_definition):
    stanza, arguments = initial_definition
    artifacts = render.build_finite_worker_artifacts(**arguments)
    worker = json.loads(artifacts['worker.json'])
    physical, = _bindings(artifacts['bindings.json'])
    bridge = BridgeConfig.from_document(json.loads(artifacts['bridge.json']))
    delta = render.build_finite_control_delta(definition_dir=FINITE_DEFINITION_DIR,
                                             worker_artifacts=artifacts)
    assert worker['native_capacity_enrollment'] == stanza
    assert stanza['enrollment_state'] == 'unenrolled'
    assert physical.host_ref == stanza['host_ref']
    assert physical.worker_source_config_digest == hashlib.sha256(artifacts['worker.json']).hexdigest()
    assert physical.worker_uid == bridge.bridge_uid == worker['worker_uid']
    assert delta['fabric_bindings_sha256'] == hashlib.sha256(artifacts['bindings.json']).hexdigest()
    assert delta['fabric_bridge_armed'] is False
    assert worker['operator_harness_armed'] is False
    assert render.build_finite_worker_artifacts(**arguments) == artifacts


def test_foreign_physical_host_cannot_consume_prepared_references(initial_definition):
    _, arguments = initial_definition
    with pytest.raises(render.AttendedDefinitionError):
        render.build_finite_worker_artifacts(**{**arguments, 'host_ref': 'host-' + '9' * 64})

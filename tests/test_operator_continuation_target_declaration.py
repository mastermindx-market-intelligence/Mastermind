"""Disabled logical target declaration; private Runtime projections only."""
import dataclasses
import json

import pytest

from control_plane.executive_runtime import StateConflict
from control_plane.runtime_binding_projection import project_runtime_binding
from control_plane.session_targets import (
    DEFAULT_TARGETS_PATH, SessionTargetError, evaluate_delivery_allowed,
    load_session_targets,
)
from control_plane.wake_transport import wake_transport_descriptor
from test_runtime_binding_projection import _admitted_runtime, _sqlite_snapshot


ALIAS = "EXECUTIVE-COO-CODEX-A"


def test_codex_declaration_is_disabled_without_retargeting_existing_owners():
    registry = load_session_targets()
    target = registry.get(ALIAS)
    assert target.target_seat == "coo"
    assert target.reasoning_surface == "codex"
    assert target.wake_transport == "codex-app-server"
    assert target.allowed_transports == ("codex-app-server",)
    assert target.target_enabled is False
    assert registry.production_armed is False
    assert registry.root_job_bindings == {}
    assert registry.resolve("coo").session_alias == "EXECUTIVE-COO-A"
    assert registry.workstream_alias_by_seat["executive"]["coo"] == "EXECUTIVE-COO-A"
    descriptor = wake_transport_descriptor(target.wake_transport)
    assert evaluate_delivery_allowed(
        production_armed=registry.production_armed,
        target_enabled=target.target_enabled,
        transport_implemented=descriptor.transport_implemented,
        binding_ready=True,
        human_required=False,
        requires_runtime_binding=descriptor.requires_runtime_binding,
    ) is False


def test_declared_target_projects_only_real_current_private_runtime_facts(tmp_path):
    runtime, _, attempt, epoch, generation, _, _ = _admitted_runtime(tmp_path)
    before = _sqlite_snapshot(runtime)
    target = load_session_targets().get(ALIAS)
    binding = project_runtime_binding(runtime, attempt.attempt_id, target)
    assert binding.session_alias == ALIAS
    assert binding.native_handle == "PROVIDER-SESSION-1"
    assert binding.binding_generation == generation.generation_number
    assert binding.reasoning_surface == "codex"
    assert _sqlite_snapshot(runtime) == before
    # Metadata declaration creates neither admission nor a Wake route.
    assert target.target_enabled is False
    with pytest.raises(StateConflict):
        project_runtime_binding(runtime, "ATT-" + "0" * 32, target)
    with pytest.raises(StateConflict):
        project_runtime_binding(runtime, attempt.attempt_id,
                                dataclasses.replace(target, target_seat="ceo"))
    with pytest.raises(StateConflict):
        project_runtime_binding(runtime, attempt.attempt_id,
                                load_session_targets().resolve("coo"))


@pytest.mark.parametrize("field", ["target_enabled", "production_armed"])
def test_source_declaration_cannot_enable_target_or_production(tmp_path, field):
    source = json.loads(DEFAULT_TARGETS_PATH.read_text())
    if field == "target_enabled":
        source["targets"][ALIAS][field] = True
    else:
        source[field] = True
    path = tmp_path / "invalid-enabled.json"
    path.write_text(json.dumps(source))
    with pytest.raises(SessionTargetError, match="must remain disabled|must be false"):
        load_session_targets(path)

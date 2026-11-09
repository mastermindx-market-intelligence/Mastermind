"""Exact kernel-incarnation behavior through legitimate launcher exec.

This is a pure failure/allow contract; no subprocess or provider is launched.
"""
import pytest

from control_plane.codex_operator_adapter import CodexAdapterError, CodexOperatorAdapter
from control_plane.operator_harness_contract import AdapterFailureClass


@pytest.mark.parametrize("launched,initialized", [
    ((12345, 1), (12345, 7)),  # same process, valid shebang/exec evolution
    ((12345, 7), (12345, 7)),
    (None, None),              # unchanged non-Darwin legacy behavior
])
def test_initialized_process_preserves_kernel_incarnation(launched, initialized):
    CodexOperatorAdapter._require_same_initialized_incarnation(
        launched, initialized
    )


@pytest.mark.parametrize("launched,initialized", [
    ((12345, 1), (67890, 1)),  # recycled PID / process substitution
    ((12345, 1), None),        # lost previously attested identity
    (None, (12345, 1)),        # unexpected identity appearance
])
def test_initialized_process_refuses_unproven_or_changed_incarnation(
    launched, initialized
):
    with pytest.raises(CodexAdapterError) as err:
        CodexOperatorAdapter._require_same_initialized_incarnation(
            launched, initialized
        )
    assert err.value.failure_class is AdapterFailureClass.PROCESS_CRASH
    assert err.value.effect_unknown is True


def test_post_initialize_exec_version_drift_still_refuses():
    """Startup exec tolerance never extends to a running accepted session."""
    from control_plane.executive_process_identity import _ProcessInstanceObservation
    from control_plane.operator_harness_contract import ProcessIdentityObservation

    adapter = object.__new__(CodexOperatorAdapter)
    expected = ProcessIdentityObservation(
        pid=123, pgid=123,
        process_start_identity="Thu Jan  1 00:00:00 1970", boot_id="boot-1"
    )
    adapter.process_identity_observer = lambda _pid: expected
    adapter.process_instance_observer = lambda _pid: _ProcessInstanceObservation(
        unique_id=33, pidversion=8
    )
    with pytest.raises(CodexAdapterError) as err:
        adapter._require_process_continuity(expected, (33, 7))
    assert err.value.failure_class is AdapterFailureClass.PROCESS_CRASH
    assert err.value.effect_unknown is True


def _exact_skill_binding_for_name_projection():
    from types import SimpleNamespace

    return SimpleNamespace(
        generation=SimpleNamespace(package_root="plugins/mastermind-operator"),
        profile=SimpleNamespace(
            write_capable=False,
            skill_grants=(
                SimpleNamespace(runtime_name="receive-commission",
                                skill_content_digest="a" * 64),
            ),
        ),
        protocol_receipt=SimpleNamespace(supports_skill_input_path=True),
    )


def test_qualified_codex_skill_observation_keeps_exact_verified_runtime_name():
    binding = _exact_skill_binding_for_name_projection()
    path = "/trusted/skills/receive-commission/SKILL.md"
    observed, mode = CodexOperatorAdapter._reduce_skill_observation(
        [{"name": "mastermind-operator:receive-commission",
          "path": path, "enabled": True}],
        skills_root="/trusted/skills", binding=binding,
    )
    assert mode == "path_precise"
    assert observed == (("receive-commission", "path_precise", path, "a" * 64),)


@pytest.mark.parametrize("provider_name", [
    "other:receive-commission",
    "mastermind-operator:receive-commission:extra",
    "mastermind-operator:ungranted",
])
def test_qualified_codex_skill_observation_refuses_foreign_names(provider_name):
    binding = _exact_skill_binding_for_name_projection()
    with pytest.raises(CodexAdapterError, match="skill_path_mismatch"):
        CodexOperatorAdapter._reduce_skill_observation(
            [{"name": provider_name, "enabled": True,
              "path": "/trusted/skills/receive-commission/SKILL.md"}],
            skills_root="/trusted/skills", binding=binding,
        )


def test_qualified_and_bare_names_of_same_grant_are_duplicate():
    binding = _exact_skill_binding_for_name_projection()
    path = "/trusted/skills/receive-commission/SKILL.md"
    with pytest.raises(CodexAdapterError, match="duplicate_skill_row"):
        CodexOperatorAdapter._reduce_skill_observation(
            [
                {"name": "receive-commission", "enabled": True, "path": path},
                {"name": "mastermind-operator:receive-commission", "enabled": True, "path": path},
            ],
            skills_root="/trusted/skills", binding=binding,
        )


def test_qualified_codex_skill_observation_refuses_path_spoofing():
    binding = _exact_skill_binding_for_name_projection()
    with pytest.raises(CodexAdapterError, match="skill_path_mismatch"):
        CodexOperatorAdapter._reduce_skill_observation(
            [{"name": "mastermind-operator:receive-commission",
              "enabled": True, "path": "/trusted/skills/evil/SKILL.md"}],
            skills_root="/trusted/skills", binding=binding,
        )


def test_writable_skill_profile_refuses_pathless_provider_catalog():
    """Write-capable agents need observed path proof, not only a Skill name."""
    binding = _exact_skill_binding_for_name_projection()
    binding.profile.write_capable = True
    with pytest.raises(CodexAdapterError, match="skill_path_attestation_unavailable"):
        CodexOperatorAdapter._reduce_skill_observation(
            [{"name": "mastermind-operator:receive-commission", "enabled": True}],
            skills_root="/trusted/skills", binding=binding,
        )


def test_readonly_skill_profile_retains_pathless_protocol_compatibility():
    binding = _exact_skill_binding_for_name_projection()
    observed, mode = CodexOperatorAdapter._reduce_skill_observation(
        [{"name": "mastermind-operator:receive-commission", "enabled": True}],
        skills_root="/trusted/skills", binding=binding,
    )
    assert mode == "pathless"
    assert observed == (("receive-commission", "pathless", None, "a" * 64),)

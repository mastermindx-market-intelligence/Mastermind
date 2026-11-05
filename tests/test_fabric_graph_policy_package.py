"""The incumbent installer must actually carry the on-demand graph reference."""
from pathlib import Path

from ops.executive_os.provider_orchestrator_policy import apply_policy, verify_policy


def test_graph_reference_is_installed_and_verified_for_both_provider_homes(tmp_path):
    home = tmp_path / "temporary-provider-home"
    home.mkdir(mode=0o700)
    result = apply_policy(home)
    assert result["state"] == "READY"
    source = Path(__file__).resolve().parents[1] / "skills" / "mastermind-fabric-orchestration"
    for directory in (".agents", ".claude"):
        installed = home / directory / "skills" / "mastermind-fabric-orchestration"
        assert (installed / "references" / "graph-engineering.md").read_bytes() == (
            source / "references" / "graph-engineering.md").read_bytes()
        assert "references/graph-engineering.md" in (installed / "SKILL.md").read_text()
    assert verify_policy(home)["state"] == "READY"


def test_graph_reference_drift_is_reported_without_repairing_the_home(tmp_path):
    home = tmp_path / "temporary-provider-home"
    home.mkdir(mode=0o700)
    apply_policy(home)
    reference = home / ".agents" / "skills" / "mastermind-fabric-orchestration" / "references" / "graph-engineering.md"
    reference.write_text("Unreviewed replacement.\n")
    before = reference.read_bytes()
    assert verify_policy(home)["state"] != "READY"
    assert reference.read_bytes() == before

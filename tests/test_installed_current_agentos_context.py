"""Actual canonical publication Event -> current DATA -> installed context child.

The incumbent fixture uses real disposable Git/Runtime/source publication and
declares inert credential, PR and Mastermind source-seal seams. This adds the
actual isolated compiler/helper path, with explicit test-only CF2 commitments.
No installed host, live token, provider, network service or socket is exercised.
"""
import base64
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest
import yaml

from control_plane import agentos_context_bundle as contract, ceo_boot_packet
from control_plane.installed_canonical_project_data_binding import read_installed_project_data
from integrations.executive_mcp import installed
from integrations.mastermind_workspace_app.contract import principal_frame
from tests.test_project_journey_canonical_create import joined
from tests.test_project_creation_source_owner import owner, env, isolated_git_env
from tests.test_installed_source_git_identity import identity
from tests.test_project_discovery_installed_plan import actual_child
from tests.test_workspace_project_git_publisher import git


def context_child(j, monkeypatch, *, after=lambda: None):
    collector, _ = actual_child(j, monkeypatch)
    # Retain the fixture's declared synthetic Mastermind source seam, encoded
    # as a digest so the context receipt has the real closed wire shape. The
    # Macro/Git generations and both compiler bodies remain actual source.
    snapshot, generation = collector._snapshot_pair, collector._generation_pair
    def fixture_seal(value):
        return value[0], value[1], hashlib.sha256(value[2].encode()).hexdigest(), value[3]
    monkeypatch.setattr(collector, "_snapshot_pair", lambda *a, **kw: fixture_seal(snapshot(*a, **kw)))
    monkeypatch.setattr(collector, "_generation_pair", lambda *a, **kw: fixture_seal(generation(*a, **kw)))
    site = Path(yaml.__file__).resolve().parent.parent
    runtime = SimpleNamespace(site_packages=site, python_binary=collector._python,
        python_version=sys.version.split()[0], python_binary_sha256="a" * 64,
        pyyaml_version=yaml.__version__, pyyaml_record_sha256="b" * 64,
        runtime_tree_sha256="c" * 64)
    monkeypatch.setattr(ceo_boot_packet, "_capacity_runtime_contract", lambda: runtime)
    monkeypatch.setattr(ceo_boot_packet, "attest_capacity_boot_runtime", lambda *a, **kw: site)
    calls = []
    original = collector._runner
    def runner(argv, **options):
        result = original(argv, **options)
        if any(str(value).endswith("/scripts/agentos_context_bundle_entry.py") for value in argv):
            calls.append((list(map(str, argv)), deepcopy(result)))
            after()
        return result
    monkeypatch.setattr(collector, "_runner", runner)
    return collector, calls


def acquire(j):
    return read_installed_project_data(j["data"].installed_binding(), principal_frame(j["workspace"]),
        operation="agentos_current_context", selection={"work_ref": j["args"]["work_ref"]})


def decode(body, work):
    assert set(body) == {"bundle_encoding", "bundle_base64", "receipt"}
    assert body["bundle_encoding"] == "base64"
    raw = base64.b64decode(body["bundle_base64"], validate=True)
    return contract.validate_current_context_read(raw, body["receipt"], work_ref=work)


def test_actual_current_data_context_uses_pinned_code_and_original_event(joined, monkeypatch):
    j = joined
    collector, calls = context_child(j, monkeypatch)
    before = j["runtime"].events.list_events()
    body, view, generation = acquire(j)
    raw, receipt = decode(body, j["args"]["work_ref"])
    assert raw == calls[0][1]["stdout"].encode()
    assert json.loads(raw)["target"]["workstream"] == j["args"]["work_ref"]
    assert receipt["compiler_code_commit"] == j["code"] != j["current"]
    assert receipt["data_commit"] == receipt["repo_sha"] == j["current"]
    assert receipt["source_mode"] == "CANONICAL_PROJECT_DATA"
    assert receipt["data_observation"]["source_operation"]["event_id"] == j["status"]["receipt"]["event_id"]
    assert receipt["bundle_sha256"] == hashlib.sha256(raw).hexdigest()
    assert view.code_commit == j["code"] and view.data_commit == j["current"]
    assert len(generation) == 64 and len(calls) == 1
    argv = calls[0][0]
    assert argv[1:4] == ["-I", "-S", "-B"]
    assert argv[argv.index("--code-root") + 1] == str(j["code_root"])
    assert argv[argv.index("--code-commit") + 1] == j["code"]
    materialized = Path(argv[argv.index("--macro-root") + 1])
    assert materialized != j["code_root"] and not materialized.exists()
    assert j["runtime"].events.list_events() == before
    assert not j["runtime"].jobs.list_jobs() and not collector._collections
    with pytest.raises(contract.AgentOsContextUnavailable):
        contract.validate_context_read(raw, receipt, work_ref=j["args"]["work_ref"])


@pytest.mark.parametrize("gate", ["read", "latest", "callback"])
def test_current_context_requires_original_independent_read_owners(joined, monkeypatch, gate):
    j = joined
    _, calls = context_child(j, monkeypatch)
    binding = j["data"].installed_binding()
    slot = j["document"]["profiles"][j["document"]["primary_profile"]]
    if gate == "read": slot["enabled"] = False
    elif gate == "latest": slot["project_canonical_data_read"] = None
    else: monkeypatch.setattr(j["data"], "read_context", lambda *a, **kw: None)
    try:
        value = read_installed_project_data(binding, principal_frame(j["workspace"]),
            operation="agentos_current_context", selection={"work_ref": j["args"]["work_ref"]})
    except (ValueError, PermissionError):
        value = None
    assert value is None and calls == []


@pytest.mark.parametrize("target", ["data_permission", "code", "default"])
def test_current_context_late_changes_withhold_original_bytes(joined, monkeypatch, target):
    j = joined
    def after():
        if target == "data_permission":
            j["document"]["profiles"][j["document"]["primary_profile"]]["project_canonical_data_read"] = None
        elif target == "code":
            source = j["code_root"] / "scripts/agentos.py"
            raw = source.read_bytes()
            source.write_bytes(raw + b"\n# transient mutation\n")
            source.write_bytes(raw)
        else:
            changed = j["integrator"] / "after-context.txt"
            changed.write_text("A distinct canonical actor moved the default.\n")
            git(j["integrator"], "add", str(changed))
            git(j["integrator"], "commit", "-m", "Move default during original capture")
            git(j["integrator"], "push", "origin", "main")
    _, calls = context_child(j, monkeypatch, after=after)
    with pytest.raises((ValueError, PermissionError, installed.GatewayError)):
        acquire(j)
    assert len(calls) == 1


def test_current_context_cannot_be_selected_without_nominal_data_scope(joined, monkeypatch):
    j = joined
    collector, calls = context_child(j, monkeypatch)
    with pytest.raises(ValueError, match="SOURCE_UNAVAILABLE"):
        collector.read_current_agentos_context(work_ref=j["args"]["work_ref"])
    assert calls == []


@pytest.mark.parametrize("field,value", [
    ("source_mode", "ADOPTED_SNAPSHOT"), ("data_commit", "f" * 40),
    ("compiler_code_commit", "e" * 40), ("unrecognized_context_proof", "IDENTICAL_CONTEXT_INPUTS"),
])
def test_closed_current_receipt_rejects_incompatible_coordinates(joined, monkeypatch, field, value):
    j = joined
    context_child(j, monkeypatch)
    body, _, _ = acquire(j)
    raw, receipt = decode(body, j["args"]["work_ref"])
    changed = deepcopy(receipt)
    changed[field] = value
    with pytest.raises(contract.AgentOsContextUnavailable):
        contract.validate_current_context_read(raw, changed, work_ref=j["args"]["work_ref"])


def existing_project(tmp_path, monkeypatch, *, source_changes=None):
    """Real nominal view with an existing C project and no publication Event."""
    from tests.test_installed_agentos_context import bound
    from tests.test_workspace_project_git_publisher import InertPullRequestOwner, AuthoredProposalCompiler
    from control_plane.workspace_project_git_publisher import FixedProjectGitPublisher, PublisherBinding
    from control_plane.executive_runtime import Runtime
    from control_plane.workspace_source_operations import SourceOperationEvents
    collector, seen = bound(tmp_path, monkeypatch, source_changes=source_changes)
    code = seen["macro"]
    # The adopted-context fixture's typed DEC intentionally uses a synthetic
    # plan source. This continuity case needs a fully resolvable real graph;
    # retain the ordinary decision, without that unrelated adoption fixture.
    decision = code / "agentos/decisions/DEC-PLAN.md"
    front = yaml.safe_load(decision.read_text().split("---", 2)[1])
    del front["project_plan_adoption"]
    decision.write_text("---\n" + yaml.safe_dump(front, sort_keys=False) + "---\nDecision fixture.\n")
    git(code, "add", "."); git(code, "commit", "-m", "Resolvable existing context fixture")
    seen["sha"] = git(code, "rev-parse", "HEAD").strip()
    git(code, "branch", "-M", "main")
    origin, writer, landing = (tmp_path / name for name in ("origin.git", "writer", "landing"))
    git(tmp_path, "clone", "--bare", str(code), str(origin))
    git(tmp_path, "clone", str(origin), str(writer))
    git(tmp_path, "clone", str(origin), str(landing))
    binding = PublisherBinding(worktree=str(writer), expected_origin=str(origin), default_branch="main",
        publisher_identity="test-current-context-reader")
    events = SourceOperationEvents(Runtime.at(tmp_path / "read-runtime").store)
    publisher = FixedProjectGitPublisher(binding, AuthoredProposalCompiler(seen["sha"]), lambda _: False,
        lambda _: "", lambda _: True, InertPullRequestOwner(origin), principal_scope=lambda _: "a" * 64,
        canonical_data_macro_root=str(code), canonical_data_code_commit=seen["sha"],
        authorize_workspace_read=lambda _: True, workspace_read_permission_stamp=lambda _: "b" * 64,
        authorize_latest_project_data=lambda _: True, latest_project_data_permission_stamp=lambda _: "c" * 64,
        canonical_data_events=events)
    def read():
        view = publisher.observe_canonical_project_data(object(), work_ref="WS:ONE")
        seen["current_view"] = view
        with view.capture_scope():
            with collector.canonical_project_data_scope(view, work_ref="WS:ONE"):
                result = collector.read_current_agentos_context(work_ref="WS:ONE")
        return result
    return collector, seen, landing, read


def test_current_context_accepts_same_code_and_data_without_a_publication(tmp_path, monkeypatch):
    collector, seen, landing, read = existing_project(tmp_path, monkeypatch)
    raw, receipt = read()
    assert receipt["compiler_code_commit"] == seen["sha"]
    assert receipt["source_mode"] == "CANONICAL_PROJECT_DATA"
    assert receipt["data_observation"]["source_operation"] is None
    assert receipt["data_commit"] == seen["sha"]
    assert b"DNR:KEEP-OWNER" in raw
    assert b"Preserve the canonical context owner" in raw
    assert not collector._collections


def test_current_context_preserves_executable_artifact_without_executing_it(tmp_path, monkeypatch):
    from tests.test_installed_agentos_context import _add_artifacts
    def source_changes(macro, seen):
        artifact = macro / "context_artifact.py"
        artifact.write_text("raise AssertionError('artifact must never execute')\n")
        artifact.chmod(0o700)
        _add_artifacts(seen, ["context_artifact.py"])
    collector, seen, _, read = existing_project(tmp_path, monkeypatch, source_changes=source_changes)
    runner = collector._runner
    modes = []
    def observe(argv, **kwargs):
        if "--macro-root" in argv:
            materialized = Path(argv[argv.index("--macro-root") + 1])
            modes.append((materialized / "context_artifact.py").stat().st_mode & 0o777)
        return runner(argv, **kwargs)
    monkeypatch.setattr(collector, "_runner", observe)
    raw, receipt = read()
    assert modes == [0o700]
    assert b"context_artifact.py" in raw
    assert receipt["data_commit"] == seen["sha"]
    assert git(seen["macro"], "ls-tree", "HEAD", "context_artifact.py").startswith("100755 blob ")


def test_event_backed_current_data_proves_its_own_history(joined, monkeypatch):
    j = joined
    collector, calls = context_child(j, monkeypatch)
    clone_database = installed._clone_git_read_database
    removed = []
    old_tree = git(j["code_root"], "rev-parse", j["code"] + "^{tree}").strip()
    current_tree = git(j["integrator"], "rev-parse", j["current"] + "^{tree}").strip()
    assert old_tree != current_tree
    def corrupt_history(source, destination, **kwargs):
        clone_database(source, destination, **kwargs)
        # Only the separate disposable N database loses one old tree. C,
        # canonical Event, HEAD tree and current blobs remain intact.
        path = destination / "objects" / old_tree[:2] / old_tree[2:]
        assert path.is_file()
        path.unlink(); removed.append(old_tree)
        assert git(destination.parent, "ls-tree", "-r", j["current"])
    monkeypatch.setattr(installed, "_clone_git_read_database", corrupt_history)
    with pytest.raises(installed.GatewayError, match="objects are incomplete"):
        acquire(j)
    assert removed == [old_tree] and calls == [] and not collector._collections


@pytest.mark.parametrize("suffix", ["^{tree}", ":agentos", ":agentos/workstreams"])
def test_current_data_requires_historical_trees_for_existing_records(tmp_path, monkeypatch, suffix):
    def history(macro, seen):
        git(macro, "add", "."); git(macro, "commit", "-m", "Historical context records")
        seen["history_commit"] = git(macro, "rev-parse", "HEAD").strip()
        record = seen["record"]
        record.write_text(record.read_text() + "A later record body.\n")
    collector, seen, _, read = existing_project(tmp_path, monkeypatch, source_changes=history)
    old_tree = git(seen["macro"], "rev-parse", seen["history_commit"] + suffix).strip()
    assert old_tree != git(seen["macro"], "rev-parse", seen["sha"] + suffix).strip()
    clone_database = installed._clone_git_read_database
    def corrupt(source, destination, **kwargs):
        clone_database(source, destination, **kwargs)
        (destination / "objects" / old_tree[:2] / old_tree[2:]).unlink()
        assert git(destination.parent, "ls-tree", "-r", seen["sha"])
    monkeypatch.setattr(installed, "_clone_git_read_database", corrupt)
    with pytest.raises(installed.GatewayError, match="objects are incomplete"):
        read()
    assert not seen["results"] and not collector._collections


@pytest.mark.parametrize("movement", ["context_config", "other_record", "unrelated"])
def test_knowledge_continuity_cannot_certify_changed_full_context(tmp_path, monkeypatch, movement):
    from control_plane.project_canonical_data import CanonicalDataUnavailable
    collector, seen, landing, read = existing_project(tmp_path, monkeypatch)
    if movement == "context_config":
        path = landing / "config/context_index.yml"
        path.write_text("projects: {foreign: {path: foreign}}\n")
    elif movement == "other_record":
        path = landing / "agentos/workstreams/WS-FOREIGN.md"
        path.write_text("---\nkey: FOREIGN\ntitle: An unrelated malformed record\n---\n")
    else:
        path = landing / "outside-context.txt"
        path.write_text("Even unchanged Knowledge inputs are not full context proof.\n")
    git(landing, "add", "."); git(landing, "commit", "-m", "Change context beyond Knowledge closure")
    git(landing, "push", "origin", "main")
    with pytest.raises((ValueError, CanonicalDataUnavailable, installed.GatewayError)):
        read()
    assert not seen["results"]
    if movement == "unrelated":
        assert "data_continuity" in seen["current_view"]._witness

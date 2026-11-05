"""Genuine temporary Git records through the actual frozen Macro source owner."""
import importlib.util
from pathlib import Path
import subprocess

import pytest

from control_plane.agentos_project_plan import read_from_macro_owner
from control_plane.ceo_boot_packet import bounded_subprocess_runner


_SPEC = importlib.util.spec_from_file_location("continuity_record_fixtures", Path(__file__).with_name("test_project_plan_continuity.py"))
_FIX = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_FIX)


@pytest.fixture
def repository(tmp_path):
    owner = _FIX.owner.__wrapped__(tmp_path)
    root = Path(owner.__file__).resolve().parents[1]
    def git(*args):
        result = subprocess.run(["git", "-C", str(root), *args], capture_output=True, check=True)
        return result.stdout
    git("init", "--quiet")
    def write(path, raw):
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
    def commit():
        git("add", ".")
        git("-c", "user.name=Plan fixture", "-c", "user.email=fixture@invalid.example", "commit", "--quiet", "-m", "Fixture only")
        return git("rev-parse", "HEAD").decode().strip()
    def put_record(path, value):
        write(path, owner._yaml_frontmatter(value).encode())
    kwargs, _, _, _, candidate, ws, _ = _FIX.inputs(owner)
    write(".gitignore", b"__pycache__/\n")
    ws["artifacts"] = []
    put_record("agentos/workstreams/WS-PLAN-TEST.md", ws)
    baseline_bytes = b"# Exact recorded base\r\n"
    write("planning/base.md", baseline_bytes)
    base_commit = commit()
    baseline = _FIX.capture("planning/base.md", baseline_bytes, base_commit)
    first = _FIX.decision("PLAN-FIRST", baseline["source"])
    put_record("agentos/decisions/DEC-PLAN-FIRST.md", first)
    commit()
    header = {"schema": "agentos.project_plan_proposal.v1", "proposal_id": "PLAN-PROPOSAL", "work_ref": _FIX.WORK,
              "base_adoption": "DEC:PLAN-FIRST", "base_source": baseline["source"],
              "candidate_sha256": _FIX.hashlib.sha256(candidate).hexdigest(), "rationale": "An actual fixture proposal.", "evidence": []}
    proposal_bytes = owner._yaml_frontmatter(header).encode() + candidate
    write("planning/proposal.md", proposal_bytes)
    ws["artifacts"] = ["macro:planning/proposal.md"]
    put_record("agentos/workstreams/WS-PLAN-TEST.md", ws)
    head = commit()
    proposal = _FIX.capture("planning/proposal.md", proposal_bytes, head)
    return locals()


def read(repo):
    calls = []
    def runner(argv, **limits):
        calls.append(argv)
        return bounded_subprocess_runner(argv, **limits)
    value = read_from_macro_owner(macro_root=repo["root"], expected_macro_sha=repo["head"],
        work_ref=_FIX.WORK, runner=runner, include_continuity=True, timeout=15)
    return value, calls


def test_real_git_owner_produces_available_v2_comparison_without_network(repository):
    value, calls = read(repository)
    assert value["schema"] == "mastermind.workspace_project_plan.v2", value
    assert value["continuity"]["adoption"]["state"] == "AVAILABLE", value
    comparison = value["continuity"]["proposals"]["items"][0]["comparison"]
    assert comparison["state"] == "AVAILABLE"
    assert comparison["base_text"].encode() == repository["baseline_bytes"]
    assert comparison["candidate_text"].encode() == repository["candidate"]
    assert any("cat-file" in call for call in calls)
    assert not any("fetch" in call or "http" in " ".join(call) for call in calls)


def test_current_decision_keeps_exact_proposal_reference_across_later_commits(repository):
    repo = repository
    repo["write"]("planning/adopted.md", repo["candidate"])
    content_commit = repo["commit"]()
    adopted = _FIX.capture("planning/adopted.md", repo["candidate"], content_commit)
    repo["first"]["superseded_by"] = "DEC:PLAN-SECOND"
    repo["put_record"]("agentos/decisions/DEC-PLAN-FIRST.md", repo["first"])
    second = _FIX.decision("PLAN-SECOND", adopted["source"], predecessor="DEC:PLAN-FIRST", proposal_source=repo["proposal"]["source"])
    repo["put_record"]("agentos/decisions/DEC-PLAN-SECOND.md", second)
    repo["head"] = repo["commit"]()
    value, _ = read(repo)
    assert value["schema"] == "mastermind.workspace_project_plan.v2", value
    assert value["continuity"]["adoption"]["state"] == "AVAILABLE", value
    item = value["continuity"]["proposals"]["items"][0]
    assert item["proposal_source"] == repo["proposal"]["source"]
    assert item["adoption_relation"] == "CURRENT_DECISION_REFERENCES_PROPOSAL"
    assert item["comparison_basis"] == "RECORDED_PREDECESSOR"
    assert item["comparison"]["state"] == "AVAILABLE"


def test_changed_proposal_bytes_are_not_aliased_to_current_decision(repository):
    repo = repository
    repo['write']('planning/adopted.md', repo['candidate'])
    content_commit = repo['commit']()
    adopted = _FIX.capture('planning/adopted.md', repo['candidate'], content_commit)
    repo['first']['superseded_by'] = 'DEC:PLAN-SECOND'
    repo['put_record']('agentos/decisions/DEC-PLAN-FIRST.md', repo['first'])
    repo['put_record']('agentos/decisions/DEC-PLAN-SECOND.md', _FIX.decision('PLAN-SECOND', adopted['source'],
        predecessor='DEC:PLAN-FIRST', proposal_source=repo['proposal']['source']))
    repo['commit']()
    candidate = repo['candidate'] + b'\nChanged proposal\n'
    header = dict(repo['header'], candidate_sha256=_FIX.hashlib.sha256(candidate).hexdigest())
    repo['write']('planning/proposal.md', repo['owner']._yaml_frontmatter(header).encode() + candidate)
    repo['head'] = repo['commit']()
    value, calls = read(repo)
    item = value['continuity']['proposals']['items'][0]
    assert item['proposal_source'] != repo['proposal']['source']
    assert item['adoption_relation'] == 'UNASSOCIATED_WITH_CURRENT_DECISION'
    assert item['comparison'] == {'state': 'UNAVAILABLE', 'reason': 'STALE_PREDECESSOR'}
    assert not any('fetch' in call for call in calls)


def test_unqualified_cross_repository_ref_is_not_read_from_same_macro_path(repository):
    repo = repository
    foreign = dict(repo['baseline']['source'], repository='mastermindx-market-intelligence/Mastermind')
    repo['first']['project_plan_adoption']['adopted_source'] = foreign
    repo['put_record']('agentos/decisions/DEC-PLAN-FIRST.md', repo['first'])
    header = dict(repo['header'], base_source=foreign)
    repo['write']('planning/proposal.md', repo['owner']._yaml_frontmatter(header).encode() + repo['candidate'])
    repo['head'] = repo['commit']()
    value, calls = read(repo)
    assert value['continuity']['adoption']['state'] == 'UNAVAILABLE'
    assert value['continuity']['adoption']['reason'] == 'SOURCE_UNAVAILABLE'
    assert value['continuity']['proposals']['items'][0]['comparison']['state'] == 'UNAVAILABLE'
    assert not any('fetch' in call or 'https://' in ' '.join(call) for call in calls)

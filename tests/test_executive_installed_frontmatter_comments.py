"""Quoted metadata hash lines must survive installed path extraction."""
import hashlib
from pathlib import Path

import pytest
import yaml

from integrations.executive_mcp.installed import (
    _build_macro_materialization_plan,
    _default_packet_runner,
    _frontmatter_lists,
    _installed_child_env,
    _materialized_macro_root,
)
from integrations.executive_mcp.schemas import GatewayError
from tests.test_executive_installed_snapshot_hardening import _git, _macro_sparse_fixture


FIXTURE = Path(__file__).parent / "fixtures/installed_macro_frontmatter/WS-PROPHET-END-TO-END-R7-2cd5.md"
PATHS = "repos: [macro]\nartifacts: [research/evidence.md]\nowns_paths: []\n"
EXPECTED = {"repos": ["macro"], "artifacts": ["research/evidence.md"], "owns_paths": []}


def parse(document):
    return _frontmatter_lists(("---\n" + document + "---\n").encode())


@pytest.mark.parametrize("metadata", [
    'title: "First wave\n  #8444 -> HK -> China (REGIONAL orchestrator)."\n',
    "title: 'First wave\n  #8444 -> HK -> China (REGIONAL orchestrator).'\n",
    'waves:\n- id: s4\n  title: "First wave\n    #8444 -> HK -> China."\n',
    'title: "First wave\n  # artifacts: [hidden]\n  Finished."\n',
    'metadata: {title: "First wave\n  # retained text",\n  done: true}\n',
    "metadata: {title: 'First wave\n  # retained ''quote''',\n  done: true}\n",
    'title: "First wave\n  # retained \\"quote\\" and ]\n  Finished."\n',
])
def test_hash_inside_quoted_metadata_is_content(metadata):
    canonical = yaml.safe_load(metadata + PATHS)
    assert {key: canonical[key] for key in EXPECTED} == EXPECTED
    assert parse(metadata + PATHS) == EXPECTED


@pytest.mark.parametrize("metadata", [
    '# "unfinished ] } &fake *missing\n',
    'title: "complete"\n  # "unfinished ] } &fake *missing\n',
    'metadata: &m "complete"\n# ] } "\ncopy: *m\n  # artifacts: [hidden]\n',
    'metadata: [\n# ] "not a closing delimiter"\n  retained,\n  # } "\n  other]\n',
    'waves:\n# artifacts: [hidden]\n- id: w1\n  # "unfinished ] }\n  title: retained\n',
])
def test_comments_outside_quotes_do_not_change_metadata_structure(metadata):
    canonical = yaml.safe_load(metadata + PATHS)
    assert {key: canonical[key] for key in EXPECTED} == EXPECTED
    assert parse(metadata + PATHS) == EXPECTED


def test_comments_at_path_list_boundaries_do_not_supply_paths():
    document = (
        "# repos: [hidden]\nrepos:\n"
        "  # artifacts: [hidden]\n  - macro\n"
        "# root comment\nartifacts:\n"
        "  - research/evidence.md\n  # 'unterminated ]\nowns_paths: []\n"
    )
    assert parse(document) == EXPECTED


@pytest.mark.parametrize("document", [
    '# comments only\n  # "unterminated\n',
    'title: "unfinished\n  # still inside quote\n' + PATHS,
    "title: 'unfinished\n  # still inside quote\n" + PATHS,
    'metadata: [retained,\n# ] comment cannot close a flow\n' + PATHS,
    'metadata: &m retained\ncopy: *m\n# comment\n  artifacts: [hidden]\n' + PATHS,
    'repos:\n  # no actual list entry\nartifacts: []\n',
])
def test_comments_do_not_relax_malformed_or_path_authority_refusals(document):
    with pytest.raises(ValueError, match="unsupported"):
        parse(document)


def test_structural_comment_whitespace_preserves_prior_behavior():
    assert parse("\t# ignored outside a quoted scalar\n" + PATHS) == EXPECTED


def test_actual_2cd5_frontmatter_preserves_quoted_hash_continuation():
    # Exact frontmatter from the configured, root-sealed 2cd5 Macro record.
    # The full source file is Git blob e21fb16f15607001e2be2bb5c7ca482aa52fbb0c.
    payload = FIXTURE.read_bytes()
    assert hashlib.sha256(payload).hexdigest() == "2b5b4b4429c64ff0b8cea6d9de5031d0c9400e5181de912e1887633642f730ea"
    canonical = yaml.safe_load(payload.decode().split("---", 2)[1])
    assert "#8444" in canonical["waves"][5]["title"]
    assert _frontmatter_lists(payload) == {
        key: canonical.get(key, []) for key in EXPECTED
    }


@pytest.mark.parametrize("metadata", [
    'metadata: "stage\n  #literal end"\n',
    "metadata: 'stage\n  #literal end'\n",
    'waves:\n  - id: stage\n    title: "adoption order\n      #8444 then next"\n    status: active\n',
    'metadata: {note: "stage\n  #literal end", copy: retained}\n',
    'metadata: &m "stage\n  #literal end"\ncopy: *m\n',
])
def test_hash_at_quoted_continuation_start_is_metadata_content(metadata):
    canonical = yaml.safe_load(metadata + PATHS)
    assert {key: canonical[key] for key in EXPECTED} == EXPECTED
    assert parse(metadata + PATHS) == EXPECTED


@pytest.mark.parametrize("document", [
    '# root comment\nmetadata: "complete"\n  # indented comment\n' + PATHS,
    'metadata: [one,\n# a comment with "] } &fake\n  two]\n' + PATHS,
    'metadata: &m retained\ncopy: *m\n  # alias has no continuation\n' + PATHS,
    'repos:\n  # list comment\n  - macro\n# between root fields\nartifacts:\n  - research/evidence.md\n  # after last item\nowns_paths: []\n',
    'metadata: |\n  # block scalar content\n  still narrative\n' + PATHS,
])
def test_unquoted_comments_remain_non_authoritative(document):
    canonical = yaml.safe_load(document)
    assert {key: canonical[key] for key in EXPECTED} == EXPECTED
    assert parse(document) == EXPECTED


@pytest.mark.parametrize("document", [
    'metadata: "unfinished\n  # still quoted\n' + PATHS,
    'metadata: [one,\n  # ] cannot finish the flow\n' + PATHS,
    'metadata: [\n  # &fake retained\n  *fake]\n' + PATHS,
    'metadata: &m "stage\n  #literal end"\nartifacts: *m\n',
    'metadata: "stage\n  #literal end"\nartifacts: [*missing]\n',
    'metadata: "stage\n  #literal end"\nrepos: [macro]\nrepos: [terminal]\n',
])
def test_comments_do_not_close_nodes_declare_aliases_or_hide_path_fields(document):
    with pytest.raises(ValueError, match="unsupported"):
        parse(document)


def _actual_record_source(tmp_path):
    macro, _ = _macro_sparse_fixture(tmp_path)
    record = macro / "agentos/workstreams/WS-SPARSE.md"
    record.write_bytes(FIXTURE.read_bytes())
    artifact = "research/prophet_v4/r7_program/PROPHET_E2E_CONTINUATION_HANDOFF_2026-10-21.md"
    target = macro / artifact
    target.parent.mkdir(parents=True)
    target.write_text("retained source evidence\n", encoding="utf-8")
    design = macro / "research/prophet_v4/r7_design/source.md"
    design.parent.mkdir(parents=True)
    design.write_text("tracked directory evidence\n", encoding="utf-8")
    _git(macro, "add", ".")
    _git(macro, "commit", "-q", "-m", "actual quoted metadata record")
    return macro, record, artifact


def test_actual_record_reaches_source_bound_materialization(tmp_path):
    macro, record, artifact = _actual_record_source(tmp_path)
    env = _installed_child_env(code_root=macro, macro_root=macro)
    plan = _build_macro_materialization_plan(
        macro, runner=_default_packet_runner, env=env, deadline=None,
    )
    assert plan.head == _git(macro, "rev-parse", "HEAD").stdout.strip()
    assert artifact in plan.files
    assert "research/prophet_v4/r7_design" in plan.directories
    assert "unrelated/large.bin" not in plan.files
    with _materialized_macro_root(macro, timeout=5.0, plan=plan) as materialized:
        assert (materialized / record.relative_to(macro)).read_bytes() == FIXTURE.read_bytes()
        assert (materialized / artifact).read_text() == "retained source evidence\n"
        assert (materialized / "research/prophet_v4/r7_design").is_dir()
        assert not (materialized / "unrelated/large.bin").exists()


def test_quoted_metadata_fix_cannot_admit_workstream_bytes_outside_head(tmp_path):
    macro, record, _ = _actual_record_source(tmp_path)
    record.write_bytes(record.read_bytes().replace(b"#8444", b"#9999"))
    env = _installed_child_env(code_root=macro, macro_root=macro)
    with pytest.raises(GatewayError) as refused:
        _build_macro_materialization_plan(
            macro, runner=_default_packet_runner, env=env, deadline=None,
        )
    assert "workstream bytes differ from HEAD" in str(refused.value.__cause__)

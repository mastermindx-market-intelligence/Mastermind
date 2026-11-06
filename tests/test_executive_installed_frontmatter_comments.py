"""Quoted metadata hash lines must survive installed path extraction."""
import pytest
import yaml

from integrations.executive_mcp.installed import _frontmatter_lists


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

"""Metadata properties must not become installed Macro path authority."""
from pathlib import Path

import pytest
import yaml

from integrations.executive_mcp.installed import _frontmatter_lists


PATHS = "repos: [macro]\nartifacts: [research/evidence.md]\nowns_paths: []\n"
EXPECTED = {"repos": ["macro"], "artifacts": ["research/evidence.md"], "owns_paths": []}


def parse(document: str):
    return _frontmatter_lists(("---\n" + document + "---\n").encode())


def test_exact_227b_chairman_record_metadata_does_not_change_paths():
    # Exact committed bytes, including all acceptance declarations and aliases.
    fixture = Path(__file__).parent / "fixtures/installed_macro_frontmatter/WS-CHAIRMAN-CONTROL-ROOM-227b.md"
    payload = fixture.read_bytes()
    canonical = yaml.safe_load(payload.decode().split("---", 2)[1])
    assert _frontmatter_lists(payload) == {
        key: canonical.get(key, []) for key in ("repos", "artifacts", "owns_paths")
    }


@pytest.mark.parametrize("metadata", [
    "metadata: &m\n  note: retained\ncopy: *m\n",
    "metadata: &m # retained\n  note: retained\ncopy: *m # no expansion\n",
    "metadata: &m\n- note\n- retained\ncopy: *m\n",
    "metadata: &m {note: retained}\ncopy: *m\n",
    "metadata: &m [retained, metadata]\ncopy: *m\n",
    "metadata: &m \"quoted\n  continued\"\ncopy: *m\n",
    "metadata: &m 'single\n  continued'\ncopy: *m\n",
    "metadata: &m |\n  artifacts: [not/a/path]\ncopy: *m\n",
    "metadata: &m {\n  note: retained,\n  refs: [other]\n  }\ncopy: *m\n",
    "metadata: {first: &m [retained], second: *m}\n",
    "metadata: &m {note: \"# and } in a quote\", # } is a comment\n  kept: true}\ncopy: *m\n",
    "waves:\n- id: W1\n  reference: &ref\n    path: research/not-materialized.md\n  retained: *ref\n",
])
def test_metadata_properties_preserve_explicit_path_fields(metadata):
    canonical = yaml.safe_load(metadata + PATHS)
    assert {key: canonical[key] for key in EXPECTED} == EXPECTED
    assert parse(metadata + PATHS) == EXPECTED


@pytest.mark.parametrize("document", [
    "metadata: &m [research/evidence.md]\nartifacts: *m\n",
    "metadata: &m [macro]\nrepos: *m\n",
    "metadata: &m [data/**]\nowns_paths: *m\n",
    "artifacts: &m [research/evidence.md]\n",
    "artifacts: [*m]\n",
    "artifacts:\n- &m research/evidence.md\n",
    "metadata: &m {repos: [macro]}\n<<: *m\n",
    "metadata: &m {repos: [macro]}\n'<<': *m\n",
    "metadata: &m\n  <<: {repos: [macro]}\n" + PATHS,
    "metadata: &m\n  '<<': {repos: [macro]}\n" + PATHS,
    "metadata: &m {<<: {repos: [macro]}}\n" + PATHS,
    "metadata: &m {'<<': {repos: [macro]}}\n" + PATHS,
    "metadata: &m {\"<<\": {repos: [macro]}}\n" + PATHS,
    "metadata: &m !!map {note: retained}\n" + PATHS,
    "metadata: &m {note: !!str retained}\n" + PATHS,
    "metadata: &m\n  note: !custom value\n" + PATHS,
    "metadata: &m\n  %YAML 1.1\n" + PATHS,
    "metadata: &m {\n%YAML 1.1\n}\n" + PATHS,
    "metadata: *missing\n" + PATHS,
    "copy: *later\nmetadata: &later value\n" + PATHS,
    "metadata: &m one\ncopy: &m two\n" + PATHS,
    "metadata: &m &other value\n" + PATHS,
    "metadata: &m *other\n" + PATHS,
    "metadata: &\n" + PATHS,
    "metadata: &" + "x" * 129 + " value\n" + PATHS,
    "metadata: &m value\ncopy: *m trailing\n" + PATHS,
    "metadata: &m value\ncopy: *m\n  artifacts: [hidden]\n" + PATHS,
    "metadata: &m {\nartifacts: [hidden]\n}\n" + PATHS,
    "metadata: &m [\nartifacts: [hidden]\n]\n" + PATHS,
    "metadata: &m \"unterminated\nartifacts: [hidden]\n\"\n" + PATHS,
    "metadata: &m 'unterminated\nartifacts: [hidden]\n'\n" + PATHS,
    "metadata: &m {note: value # } does not close the flow\n" + PATHS,
    "metadata: &m {note: value]\n" + PATHS,
    "metadata: &m [value} other\n" + PATHS,
    "metadata: &m {note: value} artifacts: [hidden]\n" + PATHS,
    "metadata: &m {note: value}\nartifacts: []\nartifacts: [hidden]\n",
    "metadata: &m {note: value}\nartifacts: []\n'artifacts': [hidden]\n",
    "metadata: &m {note: value}\n  artifacts: [hidden]\n" + PATHS,
    "metadata: &m {first: *unknown}\n" + PATHS,
])
def test_metadata_properties_cannot_supply_or_conceal_paths(document):
    with pytest.raises(ValueError, match="unsupported"):
        parse(document)


def test_metadata_anchor_name_count_is_bounded():
    document = "".join(f"note_{i}: &a{i} value\n" for i in range(257))
    with pytest.raises(ValueError, match="unsupported"):
        parse(document + PATHS)


@pytest.mark.parametrize("indent", [0, 2])
@pytest.mark.parametrize("padding", [3, 5])
@pytest.mark.parametrize("value", ['"x"', '{k: 1}', '[q]', '*m'])
def test_review_f1_padded_sequence_mapping_siblings(indent, padding, value):
    column = indent + 1 + padding
    metadata = (
        "anchor: &m retained\nmetadata:\n"
        + " " * indent + "-" + " " * padding + "first: " + value + "\n"
        + " " * column + "sibling: retained\n"
    )
    canonical = yaml.safe_load(metadata + PATHS)
    assert {key: canonical[key] for key in EXPECTED} == EXPECTED
    assert parse(metadata + PATHS) == EXPECTED


@pytest.mark.parametrize("metadata", [
    "metadata: {note: A & B}\n",
    "metadata: {note: 3 * 4}\n",
    "metadata: {note: a @ b}\n",
    "metadata: {note: use `x` here}\n",
    "metadata: {note: hi ! there}\n",
    "metadata: {note: 50 % off}\n",
    "metadata: [R&D & QA]\n",
    "metadata: {note: [a & b]}\n",
    "waves:\n  - {id: W1, title: R&D & QA}\n",
    "metadata: {note: urn:&identifier}\n",
    "metadata: {note: urn:*identifier}\n",
    "metadata: {note: urn:!identifier}\n",
    "metadata: {note: continued\n  A & B}\n",
])
def test_review_f2_flow_plain_scalar_characters_are_not_node_properties(metadata):
    canonical = yaml.safe_load(metadata + PATHS)
    assert {key: canonical[key] for key in EXPECTED} == EXPECTED
    assert parse(metadata + PATHS) == EXPECTED


@pytest.mark.parametrize("document", [
    "anchor: &m retained\nmetadata:\n-   first: *m\n      artifacts: [hidden]\n",
    "metadata:\n-   first: {k: 1}\n      artifacts: [hidden]\n",
    "metadata:\n-   first: \"x\"\n      artifacts: [hidden]\n",
    "metadata: {note: !custom value}\n",
    "metadata: {note: @value}\n",
    "metadata: {note: `value`}\n",
    "metadata: {note: %value}\n",
    "metadata: {note: # retained\n  !custom value}\n",
    "metadata: {note: # retained\n  *missing}\n",
    "metadata: [A & phantom, *phantom]\n",
    "metadata: {note: urn:&phantom, copy: *phantom}\n",
    "metadata: {note: &m retained, copy: !custom value}\n",
])
def test_review_repairs_preserve_node_and_continuation_refusals(document):
    with pytest.raises(ValueError, match="unsupported"):
        parse(document + PATHS)

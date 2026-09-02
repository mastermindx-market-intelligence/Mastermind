"""C0 falsifier — ground truth must be LSP-independent.

If ground truth came from a language server, the experiment would be grading
each candidate against itself. This census is pure `ast`: no LSP, no backend,
no network. It is also the falsifier for the hand-written answer key.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from experiments.code_intelligence.ground_truth import (
    census_definitions,
    census_diagnostics,
    census_references,
    load_answer_key,
)

CORPUS = Path("tests/fixtures/code_intelligence/python_sample")


@pytest.fixture
def answer_key() -> dict:
    return load_answer_key(CORPUS)


class TestAnswerKeyIsHonest:
    def test_declared_definitions_match_the_ast_census(self, answer_key: dict) -> None:
        declared = {
            (row["symbol"], row["relative_file"], row["line"])
            for row in answer_key["definitions"]
        }
        actual = {
            (row["symbol"], row["relative_file"], row["line"])
            for row in census_definitions(CORPUS)
        }
        assert declared == actual

    @pytest.mark.parametrize(
        "symbol",
        ["make_producer", "make_dead_producer", "consume", "LiveProducer", "DeadProducer"],
    )
    def test_declared_references_match_the_ast_census(
        self, answer_key: dict, symbol: str
    ) -> None:
        declared = {
            (row["relative_file"], row["line"])
            for row in answer_key["references"][symbol]
        }
        actual = {
            (row["relative_file"], row["line"])
            for row in census_references(CORPUS, symbol)
        }
        assert declared == actual

    def test_declared_diagnostics_match_the_ast_census(self, answer_key: dict) -> None:
        declared = [
            (row["relative_file"], row["line"], row["symbol"])
            for row in answer_key["diagnostics"]
        ]
        actual = [
            (row["relative_file"], row["line"], row["symbol"])
            for row in census_diagnostics(CORPUS)
        ]
        assert declared == actual

    def test_exactly_one_planted_diagnostic(self) -> None:
        assert len(census_diagnostics(CORPUS)) == 1


class TestCorpusDiscriminates:
    def test_dead_sibling_is_textually_similar_to_the_live_one(self) -> None:
        source = (CORPUS / "src" / "sample" / "producer.py").read_text()
        assert source.count("def produce(self) -> str:") == 3
        # A name-only grep for the method cannot separate live from dead.

    def test_consumer_imports_only_the_live_wrapper(self) -> None:
        source = (CORPUS / "src" / "sample" / "consumer.py").read_text()
        assert "make_producer" in source
        assert "make_dead_producer" not in source
        assert "DeadProducer" not in source

    def test_live_answer_is_declared(self, answer_key: dict) -> None:
        assert answer_key["live_path"]["answer"] == "LiveProducer"
        assert "DeadProducer" in answer_key["dead_siblings"]

    def test_census_is_deterministic(self) -> None:
        assert census_definitions(CORPUS) == census_definitions(CORPUS)
        assert census_references(CORPUS, "consume") == census_references(CORPUS, "consume")

    def test_census_is_sorted(self) -> None:
        rows = census_definitions(CORPUS)
        keys = [(row["relative_file"], row["line"], row["symbol"]) for row in rows]
        assert keys == sorted(keys)

    def test_answer_key_is_valid_json_on_disk(self) -> None:
        json.loads((CORPUS / "answer_key.json").read_text())

"""C0 falsifier — ground truth must be LSP-independent.

If ground truth came from a language server, the experiment would be grading
each candidate against itself. This census is pure `ast`: no LSP, no backend,
no network. It is also the falsifier for the hand-written answer key.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
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


class TestCorpusIsDataNotTests:
    """B1 — the corpus must contribute zero `tests/**/test_*.py` paths.

    The repository gate (`scripts/ci_pytest.py`) discovers with
    `rglob("test_*.py")` and then passes each path to pytest **explicitly**.
    pytest's ignore contract — `pytest_ignore_collect` and `collect_ignore`
    alike — does not apply to paths given explicitly on the command line, so no
    conftest hook can protect the corpus. The only durable guard is that the
    corpus contains no file matching `test_*.py` at all.
    """

    def _gate(self):
        spec = importlib.util.spec_from_file_location(
            "_c0_ci_pytest", Path("scripts/ci_pytest.py").resolve()
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_repository_gate_discovers_no_corpus_test_module(self) -> None:
        discovered = self._gate().discover_test_modules(Path(".").resolve())
        corpus = [p for p in discovered if "fixtures/code_intelligence" in p]
        assert corpus == [], (
            "the C0 corpus must contribute no repository test paths; the gate "
            f"passes these explicitly and pytest cannot ignore them: {corpus}"
        )

    def test_no_corpus_file_matches_the_gate_glob(self) -> None:
        offenders = sorted(
            path.as_posix()
            for path in Path("tests/fixtures/code_intelligence").rglob("test_*.py")
        )
        assert offenders == [], offenders

    def test_bounded_subprocess_collection_of_the_corpus_is_clean(self) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "tests/fixtures/code_intelligence",
             "--collect-only", "-q"],
            capture_output=True, text=True, timeout=180, shell=False,
        )
        # Exit code 5 is pytest's EXIT_NOTESTSCOLLECTED — the desired proof that
        # the corpus contributes no tests at all. A collection *error* would be 2/3.
        assert result.returncode == 5, (
            f"expected no tests collected, got rc={result.returncode}\n"
            + result.stdout[-1500:] + result.stderr[-800:]
        )
        assert "error" not in result.stdout.lower(), result.stdout[-1500:]

    def test_corpus_consumer_case_is_still_present_under_its_data_name(self) -> None:
        assert (CORPUS / "tests" / "consumer_case.py").is_file()

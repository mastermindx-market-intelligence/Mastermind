"""Reviewed executable sites are whole tokens; two reviewed examples are docstrings.

A site that covers only part of a token (for example the body of r"...") masks into an
unterminated string, and the D8 scanner then silently loses its tokenized view of the file.
"""
import ast
import hashlib
import io
import tokenize
from pathlib import Path

import pytest

from tests.executive_fabric_release_identity_review import REVIEWED_FILES
from tests.executive_identity_review import mask_reviewed_identity_literals

ROOT = Path(__file__).resolve().parents[1]
PYTHON_PATHS = tuple(path for path in REVIEWED_FILES if path.endswith(".py"))
# Exact non-executable examples in the independently reviewed, full-file-pinned
# source. This does not permit partial executable literals or arbitrary text.
DOCSTRING_SITES = {
    ("ops/executive_os/canonical_paid_definition.py", 17, 45, 57, "str", "_mastermind_"),
    ("ops/executive_os/canonical_paid_definition.py", 252, 13, 25, "str", "_mastermind_"),
}


def _tokens(source):
    return list(tokenize.generate_tokens(io.StringIO(source).readline))


@pytest.mark.parametrize("path", PYTHON_PATHS)
def test_reviewed_python_site_is_whole_token_or_exact_reviewed_docstring(path):
    source = (ROOT / path).read_text()
    assert hashlib.sha256(source.encode()).hexdigest() == REVIEWED_FILES[path]["sha256"]
    by_span = {(token.start, token.end): token for token in _tokens(source)}
    docstrings = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            if (node.body and isinstance(node.body[0], ast.Expr)
                    and isinstance(node.body[0].value, ast.Constant)
                    and type(node.body[0].value.value) is str):
                value = node.body[0].value
                docstrings.append(((value.lineno, value.col_offset),
                                   (value.end_lineno, value.end_col_offset)))
    for line, start, end, kind, spelling in REVIEWED_FILES[path]["sites"]:
        if (path, line, start, end, kind, spelling) in DOCSTRING_SITES:
            containers = [(begin, finish) for begin, finish in docstrings
                          if begin < (line, start) < (line, end) < finish]
            assert len(containers) == 1
            token = by_span[containers[0]]
            assert token.type == tokenize.STRING
            assert source.splitlines()[line - 1][start:end] == spelling
            continue
        token = by_span.get(((line, start), (line, end)))
        assert token is not None, (path, line, start, end, spelling)
        assert token.string == spelling
        assert token.type == (tokenize.STRING if kind == "str" else tokenize.NUMBER)


def test_exact_docstring_sites_are_present_in_reviewed_table():
    for path, *site in DOCSTRING_SITES:
        assert tuple(site) in REVIEWED_FILES[path]["sites"]


@pytest.mark.parametrize("site", sorted(DOCSTRING_SITES))
def test_other_partial_docstring_spans_remain_rejected(monkeypatch, site):
    path, line, start, end, kind, spelling = site
    altered = (line, start + 1, end, kind, spelling[1:])
    monkeypatch.setitem(REVIEWED_FILES, path,
                        {**REVIEWED_FILES[path], "sites": (altered,)})
    with pytest.raises(AssertionError):
        test_reviewed_python_site_is_whole_token_or_exact_reviewed_docstring(path)


def test_partial_executable_constant_remains_rejected(monkeypatch):
    path = "ops/executive_os/canonical_paid_definition.py"
    site = next(site for site in REVIEWED_FILES[path]["sites"]
                if (path, *site) not in DOCSTRING_SITES)
    line, start, end, kind, spelling = site
    altered = (line, start + 1, end, kind, spelling[1:])
    monkeypatch.setitem(REVIEWED_FILES, path,
                        {**REVIEWED_FILES[path], "sites": (altered,)})
    with pytest.raises(AssertionError):
        test_reviewed_python_site_is_whole_token_or_exact_reviewed_docstring(path)


@pytest.mark.parametrize("path", PYTHON_PATHS)
def test_masking_a_reviewed_python_file_keeps_it_tokenizable(path):
    masked = mask_reviewed_identity_literals(path, (ROOT / path).read_text())
    assert not any(token.type == tokenize.ERRORTOKEN for token in _tokens(masked))

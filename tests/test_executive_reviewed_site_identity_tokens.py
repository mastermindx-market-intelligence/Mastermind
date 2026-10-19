"""Every reviewed Python site is one whole token, so masking keeps the file tokenizable.

A site that covers only part of a token (for example the body of r"...") masks into an
unterminated string, and the D8 scanner then silently loses its tokenized view of the file.
"""
import io
import tokenize
from pathlib import Path

import pytest

from tests.executive_fabric_release_identity_review import REVIEWED_FILES
from tests.executive_identity_review import mask_reviewed_identity_literals

ROOT = Path(__file__).resolve().parents[1]
PYTHON_PATHS = tuple(path for path in REVIEWED_FILES if path.endswith(".py"))


def _tokens(source):
    return list(tokenize.generate_tokens(io.StringIO(source).readline))


@pytest.mark.parametrize("path", PYTHON_PATHS)
def test_reviewed_python_site_is_one_whole_token(path):
    source = (ROOT / path).read_text()
    by_span = {(token.start, token.end): token for token in _tokens(source)}
    for line, start, end, kind, spelling in REVIEWED_FILES[path]["sites"]:
        token = by_span.get(((line, start), (line, end)))
        assert token is not None, (path, line, start, end, spelling)
        assert token.string == spelling
        assert token.type == (tokenize.STRING if kind == "str" else tokenize.NUMBER)


@pytest.mark.parametrize("path", PYTHON_PATHS)
def test_masking_a_reviewed_python_file_keeps_it_tokenizable(path):
    masked = mask_reviewed_identity_literals(path, (ROOT / path).read_text())
    assert not any(token.type == tokenize.ERRORTOKEN for token in _tokens(masked))
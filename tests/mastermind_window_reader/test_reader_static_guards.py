import re
import shutil
import subprocess
from pathlib import Path

import pytest


READER = Path(__file__).resolve().parents[2] / 'integrations/mastermind_window_reader/static/reader.js'


def test_pr_repository_and_number_are_guarded():
    source = READER.read_text(encoding='utf-8')
    assert r'/^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/' in source
    for match in re.finditer('github.com/', source):
        assert 'validRepository' in source[max(0, match.start() - 400):match.start()]


def test_reader_javascript_parses():
    if shutil.which('node') is None:
        pytest.skip('node unavailable in this environment')
    subprocess.run(['node', '--check', str(READER)], check=True)

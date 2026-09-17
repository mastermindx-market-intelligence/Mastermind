import re
import shutil
import subprocess
import importlib
from pathlib import Path

import pytest


READER = Path(__file__).resolve().parents[2] / 'integrations/mastermind_window_reader/static/reader.js'
BROWSER_MODULES = tuple((Path(__file__).parent / name for name in (
    'test_browser.py',
    'test_live_window_browser.py',
    'test_refresh_browser.py',
    'test_signed_resource_browser.py',
)))


def test_pr_repository_and_number_are_guarded():
    source = READER.read_text(encoding='utf-8')
    assert r'/^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/' in source
    for match in re.finditer('github.com/', source):
        assert 'validRepository' in source[max(0, match.start() - 400):match.start()]
    guarded_start = source.index('if(validRepository&&validPr)')
    guarded_end = source.index('}else{', guarded_start)
    guarded_block = source[guarded_start:guarded_end]
    for sanitizer in (
        'encodeURIComponent(owner)',
        'encodeURIComponent(name)',
        'String(Number(data.lane.pr))',
    ):
        assert sanitizer in guarded_block


def test_reader_javascript_parses():
    if shutil.which('node') is None:
        pytest.skip('node unavailable in this environment')
    subprocess.run(['node', '--check', str(READER)], check=True)


def test_browser_modules_use_capability_driven_qualification():
    for module_path in BROWSER_MODULES:
        source = module_path.read_text(encoding='utf-8')
        assert 'pytest.mark.skip(' not in source
        assert 'browser_available()' in source
        assert 'pytest.mark.skipif(' in source
        assert source.index('_AVAILABLE, _REASON = browser_available()') < source.index('playwright.sync_api')
        assert source.index('pytest.mark.skipif(') < source.index('playwright.sync_api')
        assert "importorskip('playwright.sync_api'" in source
        launches = re.findall(r'chromium\.launch\([^\n]*', source)
        assert launches
        assert all(
            launch == 'chromium.launch(**browser_launch_kwargs())'
            for launch in launches
        )


def test_verify_script_refuses_output_inside_repository(tmp_path, monkeypatch):
    pytest.importorskip('jwt')
    pytest.importorskip('playwright.sync_api')
    import scripts.verify_window_browser as verifier
    repo = Path(verifier.__file__).resolve().parents[1]
    monkeypatch.chdir(repo)
    with pytest.raises(SystemExit):
        verifier.resolve_output_dir(str(repo))
    with pytest.raises(SystemExit):
        verifier.resolve_output_dir(str(repo / 'evidence'))
    with pytest.raises(SystemExit):
        verifier.resolve_output_dir('.')
    assert verifier.resolve_output_dir(str(tmp_path)) == tmp_path.resolve()


def test_browser_available_reports_missing_dependency_without_raising(monkeypatch):
    from tests.mastermind_window_reader._browser_support import (
        browser_available,
        reset_browser_available_cache,
    )

    original_import_module = importlib.import_module

    def refuse_playwright(name):
        if name == 'playwright.sync_api':
            raise ImportError('simulated absent Playwright')
        return original_import_module(name)

    reset_browser_available_cache()
    monkeypatch.setattr(importlib, 'import_module', refuse_playwright)
    try:
        available, reason = browser_available()
    finally:
        monkeypatch.undo()
        reset_browser_available_cache()
    assert available is False
    assert reason.startswith('BROWSER_UNAVAILABLE: ')

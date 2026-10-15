"""Enroll the additive earnings-reaction research tests in Mastermind's CI gate.

The repository CI intentionally collects only tests/**. Keep the substantive
research fixtures alongside their data while executing their full contract from
this one test module. This isolated child does not recurse into the repo gate.
"""
from pathlib import Path
import os
import subprocess
import sys


def test_earnings_reaction_research_contract_under_hosted_gate():
    root = Path(__file__).resolve().parents[1]
    directory = root / 'research' / 'earnings_expectations'
    sources = ('reaction_replay.py', 'replay_casebook.py', 'event_workspace_binding.py', 'expectation_owner_adapter.py', 'tiingo_manifest_inspection.py', 'amazon_management_guidance_cases.json', 'alphabet_capex_guidance.json', 'media_reported_expectations.json')
    suites = ('test_reaction_replay.py', 'test_replay_casebook.py', 'test_management_guidance_cases.py', 'test_media_witnesses.py', 'test_expectation_owner_adapter.py', 'test_owner_inspection_consumer.py', 'test_tiingo_manifest_inspection.py', 'test_pre_event_windows.py', 'test_capex_guidance_cases.py', 'test_future_bar_cutoff.py', 'test_event_workspace_binding.py', 'test_event_workspace_consumer.py')
    for name in (*sources, *suites):
        assert (directory / name).is_file(), f'missing research evidence: {name}'
    cmd = [sys.executable, '-m', 'pytest', '-q', '-p', 'no:cacheprovider', *(str(directory / name) for name in suites)]
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
    child = subprocess.run(cmd, cwd=root, capture_output=True, text=True, env=env, timeout=45, check=False)
    assert child.returncode == 0, f'{child.stdout[-4000:]}\n{child.stderr[-2000:]}'

"""Regress the accepted no-colored-edge rule in the existing portable design skill."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / 'skills/mastermind-design-system'


def test_current_accepted_container_edge_rule_reaches_all_entrypoints():
    skill = (BUNDLE / 'SKILL.md').read_text()
    components = (BUNDLE / 'references/components.md').read_text()
    states = (BUNDLE / 'references/states-accessibility.md').read_text()
    assert 'no colored container-edge accents' in skill
    assert '3px semantic rail' not in components
    assert '3px rail' not in states
    assert 'even neutral border' in components
    assert 'keyboard focus outlines' in skill
    assert 'Quiet neutral fill' in states


def test_projection_preserves_original_tokens_and_source_lineage():
    manifest = json.loads((BUNDLE / 'manifest.json').read_text())
    assert manifest['source']['macro_design_authority']['commit'] == 'a136a9e67f0e435a495e1b86a63eaa924e23b683'
    assert manifest['method_reconciliation']['commit'] == '7ed871335f980fb3d0b0483b13ad5b6072cdda6d'
    assert manifest['method_reconciliation']['token_projection_refreshed'] is False
    assert manifest['method_reconciliation']['paper_reverified'] is False
    expected = {'tokens/mastermind.css': 'fef8a4eb646a024be1ef2c1439e0470889b24e871c9cdcd35088eeac12ebbdba',
                'tokens/mastermind.tokens.json': '8aab3e7de3f1adcb74b5320306f333eda9c00bbedf474ccfcb7d6d203a36308c'}
    for name, digest in expected.items():
        assert hashlib.sha256((BUNDLE / name).read_bytes()).hexdigest() == digest
    tokens = json.loads((BUNDLE / 'tokens/mastermind.tokens.json').read_text())['tokens']
    assert len(tokens) == 115
    assert 'portable reference projection' in (BUNDLE / 'SKILL.md').read_text()


def test_existing_bundle_validator_and_hash_census():
    result = subprocess.run([sys.executable, str(BUNDLE / 'scripts/validate_bundle.py')],
                            capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stdout + result.stderr
    census = json.loads((BUNDLE / 'SHA256SUMS.json').read_text())
    actual = {str(path.relative_to(BUNDLE)): hashlib.sha256(path.read_bytes()).hexdigest()
              for path in BUNDLE.rglob('*')
              if path.is_file() and path.name != 'SHA256SUMS.json' and '__pycache__' not in path.parts}
    assert actual == census
    assert 'agents/openai.yaml' in census
    assert not any(name.endswith(('.woff', '.woff2', '.ttf', '.otf')) for name in census)

"""One unchanged traversal bound; source/site drift restores ordinary identity scanning."""
from pathlib import Path
from tests.test_ceo_submit_armed_composition import _scan_added_identity_diff, _d8_frozen_source_diff

PATH = 'app/mastermind_os/src/admission/project-admission-command-port.ts'


def test_json_node_budget_is_exact_and_never_a_generic_numeric_exemption():
    source = (Path(__file__).resolve().parents[1] / PATH).read_text()
    assert 'budget = {left: 400}' in source
    assert _scan_added_identity_diff(_d8_frozen_source_diff(PATH, source), source_postimages={PATH: source}) == []
    changed = source.replace('budget = {left: 400}', 'budget = {left: 401}', 1)
    assert _scan_added_identity_diff(_d8_frozen_source_diff(PATH, changed), source_postimages={PATH: changed}) == ['401']
    changed = source + '\nconst peerUid = 400;\n'
    findings = _scan_added_identity_diff(_d8_frozen_source_diff(PATH, changed), source_postimages={PATH: changed})
    assert findings == ['400', '400']  # Byte drift exposes both budget and new identity literal.

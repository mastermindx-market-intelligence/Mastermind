"""Test-owned exact donor literal review data and drift canaries.

The incumbent finite table imports these frozen records. No scanner rule,
source-directory exclusion or runtime identity/authority is introduced.
"""
from pathlib import Path

import pytest

REVIEWED_FILES = {
    # Hermes 1c0cd667 MIT source archives: attended parent and independent
    # principal source inspection classified exactly six HTTP status operands,
    # one Path.mkdir permission default and one HTTPS default port. These are
    # not Mastermind identities. No production semantics or scanner rules change;
    # every byte/path/token drift returns all sites to the ordinary scanner.
    'integrations/hermes_qualification/workspace_oauth_privacy/fixtures/hermes_cli__mcp_config.py.source': {
        'sha256': 'bd017489bfbb2769f73572ed6627b67e61838d8af162bf3072cc664d9a31f696',
        'sites': ((811, 101, 104, 'int', '401'), (811, 106, 109, 'int', '403'),
                  (826, 97, 100, 'int', '401'), (826, 102, 105, 'int', '403')),
    },
    'integrations/hermes_qualification/workspace_oauth_privacy/fixtures/hermes_dir_acl.py.source': {
        'sha256': 'd978e1fbddffd05f4506e9c6d80a279ac9d5fea799d9a3174b260a7ff02bb50e',
        'sites': ((407, 48, 53, 'int', '0o777'),),
    },
    'integrations/hermes_qualification/workspace_oauth_privacy/fixtures/tools__mcp_tool_errors.py.source': {
        'sha256': '7f9a13601314b420119b7b633e48be69117827a784c1c980fddeb80e08ef95a8',
        'sites': ((186, 86, 89, 'int', '401'), (186, 91, 94, 'int', '403')),
    },
    'integrations/hermes_qualification/workspace_oauth_privacy/fixtures/utils.py.source': {
        'sha256': '9c4751dc9fbcbfe7e16d9e0cc5fb25566517c4927d2dc84061d4cac993a98445',
        'sites': ((785, 40, 43, 'int', '443'),),
    },
}


@pytest.mark.parametrize("filename", ["hermes_cli__mcp_config.py.source", "hermes_dir_acl.py.source",
                                    "tools__mcp_tool_errors.py.source", "utils.py.source"])
def test_exact_donor_literal_review_does_not_hide_source_or_identity_drift(filename):
    from tests.executive_identity_review import reviewed_literal_spans
    from tests.test_ceo_submit_armed_composition import _scan_added_identity_diff, _d8_frozen_source_diff
    path = "integrations/hermes_qualification/workspace_oauth_privacy/fixtures/" + filename
    text = (Path(__file__).resolve().parents[1] / path).read_text()
    assert reviewed_literal_spans(path, text)
    assert _scan_added_identity_diff(_d8_frozen_source_diff(path, text), source_postimages={path: text}) == []
    for changed in (text + "\n# unrelated byte drift\n", text + "\nnew_peer_uid = 471\n"):
        assert reviewed_literal_spans(path, changed) == ()
        findings = _scan_added_identity_diff(_d8_frozen_source_diff(path, changed), source_postimages={path: changed})
        assert findings
        if "new_peer_uid" in changed:
            assert "471" in findings

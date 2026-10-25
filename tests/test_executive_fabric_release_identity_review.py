"""Exact reviewed Fabric release tokens, including retained and shell source."""
from pathlib import Path

import pytest

from tests.executive_fabric_release_identity_review import REVIEWED_FILES
from tests.executive_identity_review import reviewed_literal_spans
from tests.test_executive_a2_identity_review import scan


@pytest.mark.parametrize('path', tuple(REVIEWED_FILES))
def test_only_exact_reviewed_file_and_spelling_qualifies(path):
    text = (Path(__file__).parents[1]/path).read_text()
    spans = reviewed_literal_spans(path, text)
    assert len(spans) == len(REVIEWED_FILES[path]['sites'])
    # Full-file scanning still exposes pre-existing topology names/modes;
    # those unchanged lines are outside the branch diff and this review.
    expected = (['_mastermind_exec', '_mastermind_exec', '_mastermind_worker',
        '_mastermind_worker', '_mastermind_ops'] if path in {
            'ops/executive_os/acceptance.py', 'ops/executive_os/bootstrap-host.sh'} else
        ['_mastermind_executive_mcp', '_mastermind_exec', '_mastermind_exec',
         '_mastermind_worker', '0o644', '_mastermind_worker'] if path ==
        'ops/executive_os/autonomy_control.py' else [])
    assert scan(text, path) == expected
    assert reviewed_literal_spans('unreviewed/'+path, text) == ()


@pytest.mark.parametrize('path', tuple(REVIEWED_FILES))
def test_changed_or_extended_file_cannot_reuse_review(path):
    text = (Path(__file__).parents[1]/path).read_text()
    changed = text+'\nnew_peer_uid = 471\n'
    assert reviewed_literal_spans(path, changed) == ()
    assert '471' in scan(changed, path)
    line, start, end, _, spelling = REVIEWED_FILES[path]['sites'][0]
    lines = text.splitlines(keepends=True)
    assert lines[line-1][start:end] == spelling
    lines[line-1] = lines[line-1][:start]+'0'+lines[line-1][end:]
    assert reviewed_literal_spans(path, ''.join(lines)) == ()


@pytest.mark.parametrize('path', [
    'ops/executive_os/bootstrap-host.sh',
    'integrations/session_bridge/original_validator_compat/artifact_delivery.py.base',
])
def test_non_python_review_still_requires_exact_diff_postimage(path):
    from tests.test_ceo_submit_armed_composition import _scan_added_identity_diff
    text = (Path(__file__).parents[1]/path).read_text()
    diff = f'+++ b/{path}\n@@ -0,0 +1,1 @@\n+different source\n'
    with pytest.raises(AssertionError, match='diff/postimage line mismatch'):
        _scan_added_identity_diff(diff, source_postimages={path: text})

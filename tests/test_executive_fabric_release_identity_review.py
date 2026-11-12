"""Exact reviewed Fabric release tokens, including retained and shell source."""
from pathlib import Path

import pytest

from tests.executive_fabric_release_identity_review import REVIEWED_FILES
from tests.executive_identity_review import reviewed_literal_spans
from tests.test_executive_a2_identity_review import scan


def test_preview_block_unit_pin_exposes_even_nonidentity_byte_drift():
    from tests.test_ceo_submit_armed_composition import (
        _d8_frozen_source_diff, _scan_added_identity_diff,
    )
    path = 'ops/fleet_storage_cleanup/linux_cache_preview.py'
    text = (Path(__file__).parents[1] / path).read_text()
    assert reviewed_literal_spans(path, text) == ((204, 43, 46, 'int'),)
    assert _scan_added_identity_diff(
        _d8_frozen_source_diff(path, text), source_postimages={path: text},
    ) == []
    changed = text + '\n# unrelated byte drift\n'
    assert reviewed_literal_spans(path, changed) == ()
    assert _scan_added_identity_diff(
        _d8_frozen_source_diff(path, changed), source_postimages={path: changed},
    ) == ['512']


@pytest.mark.parametrize('path', tuple(REVIEWED_FILES))
def test_only_exact_reviewed_file_and_spelling_qualifies(path):
    text = (Path(__file__).parents[1]/path).read_text()
    spans = reviewed_literal_spans(path, text)
    assert len(spans) == (len(REVIEWED_FILES[path]['sites'])
                          + len(REVIEWED_FILES[path].get('utf8_sites', ())))
    # Full-file scanning still exposes pre-existing topology names/modes;
    # those unchanged lines are outside the branch diff and this review.
    expected = (['_mastermind_exec', '_mastermind_exec', '_mastermind_worker',
        '_mastermind_worker', '_mastermind_ops'] if path in {
            'ops/executive_os/acceptance.py', 'ops/executive_os/bootstrap-host.sh'} else
        ['_mastermind_executive_mcp', '_mastermind_exec', '_mastermind_exec',
         '_mastermind_worker', '0o644', '_mastermind_worker'] if path ==
        'ops/executive_os/autonomy_control.py' else
        ['_mastermind_operator_canary', '0o700'] if path ==
        'control_plane/codex_operator_adapter.py' else
        ['430', '512', '401', '403', '409', '503', '503', '503', '503'] if path ==
        'app/mastermind_os/src-tauri/src/auth.rs' else
        # Exact protected installer60fb9e55 retains these17 findings unchanged;
        # only the newly reviewed initial directory-mode token is masked.
        ['_mastermind_exec', '_mastermind_exec', '_mastermind_worker',
         '_mastermind_worker', '_mastermind_ops', '_mastermind_ops',
         '_mastermind_ops', '_mastermind_ops', '452', '457',
         '_mastermind_worker', '_mastermind_worker', '452', '432', '457',
         '432', '432'] if path == 'ops/executive_os/install.sh' else
        # Incumbent provider findings remain visible; only the ten new exact
        # subscription principal sites are qualified by this source record.
        ["_mastermind_worker","451","_mastermind_","_mastermind_worker","451","453","453","400","500","400","500","451","453","453"] if path ==
        'ops/executive_os/provider_worker_slots.py' else [])
    assert scan(text, path) == expected
    assert reviewed_literal_spans('unreviewed/'+path, text) == ()


@pytest.mark.parametrize('path', tuple(REVIEWED_FILES))
def test_changed_or_extended_file_cannot_reuse_review(path):
    text = (Path(__file__).parents[1]/path).read_text()
    changed = text+'\nnew_peer_uid = 471\n'
    assert reviewed_literal_spans(path, changed) == ()
    assert '471' in scan(changed, path)
    record = REVIEWED_FILES[path]
    if record['sites']:
        line, start, end, _, spelling = record['sites'][0]
        lines = text.splitlines(keepends=True)
        assert lines[line-1][start:end] == spelling
        lines[line-1] = lines[line-1][:start]+'0'+lines[line-1][end:]
        mutated = ''.join(lines)
    else:
        line, start, end, _, spelling = record['utf8_sites'][0]
        lines = text.encode('utf-8').splitlines(keepends=True)
        assert lines[line-1][start:end] == spelling.encode('ascii')
        lines[line-1] = lines[line-1][:start]+b'0'+lines[line-1][end:]
        mutated = b''.join(lines).decode('utf-8')
    assert reviewed_literal_spans(path, mutated) == ()


@pytest.mark.parametrize('path', [
    'ops/executive_os/bootstrap-host.sh',
    'integrations/session_bridge/original_validator_compat/artifact_delivery.py.base',
    'research/fabric_glm_account_admission_20261014/BASELINE.xml',
    'review_evidence/fabric_application/shared-relay-source-qualification-20261107.json',
    'review_evidence/fabric_application/protected-hermes-readiness-join-20261107.json',
])
def test_non_python_review_still_requires_exact_diff_postimage(path):
    from tests.test_ceo_submit_armed_composition import _scan_added_identity_diff
    text = (Path(__file__).parents[1]/path).read_text()
    diff = f'+++ b/{path}\n@@ -0,0 +1,1 @@\n+different source\n'
    with pytest.raises(AssertionError, match='diff/postimage line mismatch'):
        _scan_added_identity_diff(diff, source_postimages={path: text})


_FROZEN_GLM_DURATIONS = (
    ("research/fabric_glm_account_admission_20261014/baseline.quota_remote.py",
     (22, 10, 13, "int"), "FRESH_S = 600", "new_peer_uid = 600"),
    ("research/fabric_glm_account_admission_20261014/quota_remote.py",
     (22, 10, 13, "int"), "FRESH_S = 600", "new_peer_uid = 600"),
    ("research/fabric_glm_account_admission_20261014/BASELINE.xml",
     (19, 46, 49, "int"), "ttl=600", "uid=600"),
)


@pytest.mark.parametrize("path,site,duration,identity", _FROZEN_GLM_DURATIONS)
def test_frozen_glm_duration_requires_complete_matching_postimage(
    path, site, duration, identity,
):
    from tests.test_ceo_submit_armed_composition import (
        _d8_frozen_source_diff, _scan_added_identity_diff,
    )
    text = (Path(__file__).parents[1] / path).read_text()
    diff = _d8_frozen_source_diff(path, text)
    assert reviewed_literal_spans(path, text) == (site,)
    assert _scan_added_identity_diff(diff, source_postimages={path: text}) == []
    assert "600" in _scan_added_identity_diff(diff)
    # A complete source pin cannot bless diff lines from another postimage.
    changed = text.replace(duration, identity, 1)
    assert changed != text
    with pytest.raises(AssertionError, match="diff/postimage line mismatch"):
        _scan_added_identity_diff(diff, source_postimages={path: changed})


@pytest.mark.parametrize("path,site,duration,identity", _FROZEN_GLM_DURATIONS)
def test_frozen_glm_duration_cannot_change_into_an_identity(
    path, site, duration, identity,
):
    text = (Path(__file__).parents[1] / path).read_text()
    changed = text.replace(duration, identity, 1)
    assert changed != text
    assert reviewed_literal_spans(path, changed) == ()
    assert "600" in scan(changed, path)


@pytest.mark.parametrize("path,site,duration,identity", _FROZEN_GLM_DURATIONS)
@pytest.mark.parametrize("suffix,finding", [
    ("\nnew_peer_uid = 471\n", "471"),
    ('\nnew_account = "_mastermind_account"\n', "_mastermind_account"),
])
def test_frozen_glm_duration_does_not_exempt_extra_identity(
    path, site, duration, identity, suffix, finding,
):
    text = (Path(__file__).parents[1] / path).read_text()
    changed = text + suffix
    assert reviewed_literal_spans(path, changed) == ()
    findings = scan(changed, path)
    assert "600" in findings
    assert finding in findings


@pytest.mark.parametrize("path,site,duration,identity", _FROZEN_GLM_DURATIONS)
def test_frozen_glm_duration_requires_its_exact_registered_pin(
    monkeypatch, path, site, duration, identity,
):
    text = (Path(__file__).parents[1] / path).read_text()
    monkeypatch.delitem(REVIEWED_FILES, path)
    assert reviewed_literal_spans(path, text) == ()
    assert "600" in scan(text, path)


@pytest.mark.parametrize("path,site,duration,identity", _FROZEN_GLM_DURATIONS)
@pytest.mark.parametrize("with_identity", [False, True])
def test_frozen_glm_duration_real_committed_git_collector(
    tmp_path, monkeypatch, path, site, duration, identity, with_identity,
):
    from tests import test_ceo_submit_armed_composition as guard
    content = (Path(__file__).parents[1] / path).read_text()
    if with_identity:
        content += "\nnew_peer_uid = 471\n"
        assert "471" in scan(content, path)
    # Reuse the incumbent disposable Git fixture and real collector. It commits
    # exact postimages and invokes the owning topology guard through git diff/show.
    guard.test_d8_real_git_diff_distinguishes_evidence_from_identity_changes(
        tmp_path, monkeypatch, path, content, with_identity,
    )


_OFFICE_TIMING_FIXTURE = (
    'integrations/studio_direct_mcp/search-runtime/test-issue1027-office.mjs'
)


def test_office_timing_pin_requires_exact_complete_postimage():
    from tests.test_ceo_submit_armed_composition import (
        _d8_frozen_source_diff, _scan_added_identity_diff,
    )

    path = _OFFICE_TIMING_FIXTURE
    text = (Path(__file__).parents[1] / path).read_text()
    diff = _d8_frozen_source_diff(path, text)
    assert reviewed_literal_spans(path, text) == (
        (97, 67, 70, 'int'), (98, 55, 58, 'int'), (131, 97, 100, 'int'),
    )
    assert _scan_added_identity_diff(diff, source_postimages={path: text}) == []
    assert {'900', '850'} <= set(_scan_added_identity_diff(diff))
    changed = text + '\n// unrelated byte drift\n'
    assert reviewed_literal_spans(path, changed) == ()
    assert {'900', '850'} <= set(_scan_added_identity_diff(
        _d8_frozen_source_diff(path, changed), source_postimages={path: changed},
    ))
    # A mismatched added line is distinct from an unrelated trailing byte:
    # the latter already invalidates the full-file pin above.
    lines = text.splitlines(keepends=True)
    lines[96] = lines[96][:67] + '901' + lines[96][70:]
    with pytest.raises(AssertionError, match='diff/postimage line mismatch'):
        _scan_added_identity_diff(diff, source_postimages={path: ''.join(lines)})


def test_office_timing_pin_requires_its_exact_registered_record(monkeypatch):
    from tests.test_ceo_submit_armed_composition import (
        _d8_frozen_source_diff, _scan_added_identity_diff,
    )

    path = _OFFICE_TIMING_FIXTURE
    text = (Path(__file__).parents[1] / path).read_text()
    monkeypatch.delitem(REVIEWED_FILES, path)
    assert reviewed_literal_spans(path, text) == ()
    assert {'900', '850'} <= set(_scan_added_identity_diff(
        _d8_frozen_source_diff(path, text), source_postimages={path: text},
    ))


@pytest.mark.parametrize('with_identity', [False, True])
def test_office_timing_pin_real_committed_git_collector(tmp_path, monkeypatch, with_identity):
    from tests import test_ceo_submit_armed_composition as guard

    path = _OFFICE_TIMING_FIXTURE
    content = (Path(__file__).parents[1] / path).read_text()
    if with_identity:
        content += '\nnew_peer_uid = 471\n'
        assert '471' in scan(content, path)
    # The incumbent fixture commits exact source, collects diff/show postimages,
    # and invokes the actual D8 topology guard; no scanner rule changes here.
    guard.test_d8_real_git_diff_distinguishes_evidence_from_identity_changes(
        tmp_path, monkeypatch, path, content, with_identity,
    )

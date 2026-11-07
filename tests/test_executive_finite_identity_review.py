"""Fixed finite identity review never relaxes the generic D8 source guard."""
from pathlib import Path

import pytest

from tests.executive_identity_review import reviewed_literal_spans
from tests.test_executive_a2_identity_review import scan

STAGE = 'ops/executive_os/attended_control_staging.py'
REGISTER = 'control_plane/fabric_attended_registration.py'
RETIRE = 'ops/executive_os/attended_control_retirement.py'


@pytest.mark.parametrize('path,count', [(STAGE, 7), (REGISTER, 1), (RETIRE, 7)])
def test_exact_review_preserves_scan_of_other_identity(path, count):
    text = (Path(__file__).parents[1]/path).read_text()
    assert len(reviewed_literal_spans(path, text)) == count
    assert scan(text, path) == []
    assert scan(text+'\nnew_peer_uid = 471\n', path) == ['471']
    assert reviewed_literal_spans('ops/executive_os/foreign.py', text) == ()


@pytest.mark.parametrize('path,before,after', [
    (STAGE, '!= 470', '!= 471'),
    (STAGE, "'_mastermind_minimax'", "'_mastermind_other'"),
    (STAGE, 'identity.pw_uid !=', 'identity.pw_uid =='),
    (STAGE, "'finite principal is not quiescent'", "'changed semantics'"),
    (REGISTER, "'_mastermind_minimax'", "'_mastermind_other'"),
    (REGISTER, "label = 'mastermind-minimax'", "label = 'another-account'"),
    (REGISTER, '    guard()\n    if existing', '    if existing'),
    (RETIRE, '!= 470', '!= 471'),
    (RETIRE, "'_mastermind_minimax'", "'_mastermind_other'"),
    (RETIRE, 'self.require_service_uids_quiescent()', 'self.require_services_already_stopped()'),
    (RETIRE, 'self._active_transaction is not tx', 'self._active_transaction is tx'),
])
def test_semantic_or_identity_drift_exposes_entire_anchor(path, before, after):
    text = (Path(__file__).parents[1]/path).read_text()
    assert before in text
    changed = text.replace(before, after)
    assert reviewed_literal_spans(path, changed) == ()
    assert scan(changed, path)


def test_exact_lifecycle_identity_pins_require_entire_reviewed_source():
    path = 'ops/executive_os/finite_service_lifecycle.py'
    text = (Path(__file__).parents[1]/path).read_text()
    spans = reviewed_literal_spans(path, text)
    assert len(spans) == 37
    assert scan(text, path) == []
    assert reviewed_literal_spans('ops/executive_os/foreign.py', text) == ()
    for line, start, end, kind in spans:
        lines = text.splitlines(keepends=True)
        replacement = '471' if kind == 'int' else '"_mastermind_other"'
        lines[line - 1] = lines[line - 1][:start] + replacement + lines[line - 1][end:]
        changed = ''.join(lines)
        assert reviewed_literal_spans(path, changed) == ()
        assert scan(changed, path)
    for suffix in ('\nnew_peer_uid = 471\n', '\n# source drift\n'):
        assert reviewed_literal_spans(path, text + suffix) == ()
        assert scan(text + suffix, path)


# Static review evidence lives with the tests, as for finite-initial review.
REVIEWED_ANCHORS_BY_PATH = {'ops/executive_os/attended_control_staging.py': {'ProductionFiniteStagingHost': {'node_type': 'ClassDef',
                                                                                  'ast_sha256': '98d53c9f9a0f307b0b17c68792e64d053cd8a307ec39440fcc2564b2bacde698',
                                                                                  'sites': ((('body',
                                                                                              8,
                                                                                              'body',
                                                                                              8,
                                                                                              'value',
                                                                                              'args',
                                                                                              0),
                                                                                             'str',
                                                                                             '_mastermind_minimax',
                                                                                             "'_mastermind_minimax'"),
                                                                                            (('body',
                                                                                              8,
                                                                                              'body',
                                                                                              9,
                                                                                              'test',
                                                                                              'values',
                                                                                              0,
                                                                                              'comparators',
                                                                                              0),
                                                                                             'int',
                                                                                             470,
                                                                                             '470'),
                                                                                            (('body',
                                                                                              8,
                                                                                              'body',
                                                                                              9,
                                                                                              'test',
                                                                                              'values',
                                                                                              1,
                                                                                              'comparators',
                                                                                              0),
                                                                                             'int',
                                                                                             470,
                                                                                             '470'),
                                                                                            (('body',
                                                                                              8,
                                                                                              'body',
                                                                                              9,
                                                                                              'test',
                                                                                              'values',
                                                                                              2,
                                                                                              'comparators',
                                                                                              0),
                                                                                             'int',
                                                                                             470,
                                                                                             '470'),
                                                                                            (('body',
                                                                                              8,
                                                                                              'body',
                                                                                              9,
                                                                                              'test',
                                                                                              'values',
                                                                                              3,
                                                                                              'comparators',
                                                                                              0),
                                                                                             'int',
                                                                                             470,
                                                                                             '470'),
                                                                                            (('body',
                                                                                              8,
                                                                                              'body',
                                                                                              9,
                                                                                              'test',
                                                                                              'values',
                                                                                              4,
                                                                                              'comparators',
                                                                                              0),
                                                                                             'str',
                                                                                             '_mastermind_minimax',
                                                                                             "'_mastermind_minimax'"),
                                                                                            (('body',
                                                                                              8,
                                                                                              'body',
                                                                                              12,
                                                                                              'test',
                                                                                              'args',
                                                                                              0),
                                                                                             'int',
                                                                                             470,
                                                                                             '470'))}},
 'control_plane/fabric_attended_registration.py': {'register_fixed_finite': {'node_type': 'FunctionDef',
                                                                             'ast_sha256': '8e97b9a0ba1adb3fa58e9497fb21b41cbf2fc5972efdae9626ec656d105d81e6',
                                                                             'sites': ((('body',
                                                                                         11,
                                                                                         'test',
                                                                                         'comparators',
                                                                                         0),
                                                                                        'str',
                                                                                        '_mastermind_minimax',
                                                                                        "'_mastermind_minimax'"),)}},
 'ops/executive_os/attended_control_retirement.py': {'ProductionFiniteRetirementHost': {'node_type': 'ClassDef',
                                                                                        'ast_sha256': 'd13369cc416a1a245f7e2487c791fd5807210fb940c65119c04b25bb1457add9',
                                                                                        'sites': ((('body',
                                                                                                    8,
                                                                                                    'body',
                                                                                                    4,
                                                                                                    'value',
                                                                                                    'args',
                                                                                                    0),
                                                                                                   'str',
                                                                                                   '_mastermind_minimax',
                                                                                                   "'_mastermind_minimax'"),
                                                                                                  (('body',
                                                                                                    8,
                                                                                                    'body',
                                                                                                    5,
                                                                                                    'test',
                                                                                                    'values',
                                                                                                    0,
                                                                                                    'comparators',
                                                                                                    0),
                                                                                                   'int',
                                                                                                   470,
                                                                                                   '470'),
                                                                                                  (('body',
                                                                                                    8,
                                                                                                    'body',
                                                                                                    5,
                                                                                                    'test',
                                                                                                    'values',
                                                                                                    1,
                                                                                                    'comparators',
                                                                                                    0),
                                                                                                   'int',
                                                                                                   470,
                                                                                                   '470'),
                                                                                                  (('body',
                                                                                                    8,
                                                                                                    'body',
                                                                                                    5,
                                                                                                    'test',
                                                                                                    'values',
                                                                                                    2,
                                                                                                    'comparators',
                                                                                                    0),
                                                                                                   'int',
                                                                                                   470,
                                                                                                   '470'),
                                                                                                  (('body',
                                                                                                    8,
                                                                                                    'body',
                                                                                                    5,
                                                                                                    'test',
                                                                                                    'values',
                                                                                                    3,
                                                                                                    'comparators',
                                                                                                    0),
                                                                                                   'int',
                                                                                                   470,
                                                                                                   '470'),
                                                                                                  (('body',
                                                                                                    8,
                                                                                                    'body',
                                                                                                    5,
                                                                                                    'test',
                                                                                                    'values',
                                                                                                    4,
                                                                                                    'comparators',
                                                                                                    0),
                                                                                                   'str',
                                                                                                   '_mastermind_minimax',
                                                                                                   "'_mastermind_minimax'"),
                                                                                                  (('body',
                                                                                                    8,
                                                                                                    'body',
                                                                                                    8,
                                                                                                    'test',
                                                                                                    'args',
                                                                                                    0),
                                                                                                   'int',
                                                                                                   470,
                                                                                                   '470'))}}}

"""Exact catalog-status pins preserve all identity and admission drift guards."""
import ast
from pathlib import Path

import pytest

from tests.executive_identity_review import (
    mask_reviewed_identity_literals, reviewed_literal_spans,
)
from tests.test_ceo_submit_armed_composition import _scan_added_identity_diff
from tests.test_executive_identity_review import _replace_span, _scan


ROOT = Path(__file__).resolve().parents[1]
SERVICE_PATH = "control_plane/executive_service.py"
BACKEND_PATH = "control_plane/paid_fabric_backend.py"
SOURCE = (ROOT / SERVICE_PATH).read_text()
OWNER = next(node for node in ast.parse(SOURCE).body
             if isinstance(node, ast.ClassDef) and node.name == "ExecutiveControlService")
METHOD = next(node for node in OWNER.body
              if isinstance(node, ast.AsyncFunctionDef)
              and node.name == "_handle_ceo_ingress_connection")
BLOCK = "".join(SOURCE.splitlines(keepends=True)[METHOD.lineno - 1:METHOD.end_lineno])
FRAGMENT = "class ExecutiveControlService:\n" + BLOCK + "\n"
# Model READ and selected-child composition move the same three status operands.
STATUS_SITES = ((6002, 66, 69, 'int'), (6015, 74, 77, 'int'), (6017, 75, 78, 'int'))

BACKEND_SITES = (
    (226, 73, 76, "int"),
    (416, 78, 81, "int"),
    (511, 83, 86, "int"),
)

def _assert_catalog_refused(source):
    spans = reviewed_literal_spans(SERVICE_PATH, source)
    # The separate historical Company-method record remains available; no
    # catalog status or identity token may be hidden by a changed ingress pin.
    assert all(source.splitlines()[line - 1][start:end] == "0o710"
               for line, start, end, _ in spans)
    assert len(spans) <= 3
    expected = source
    for span in reversed(spans):
        expected = _replace_span(expected, span, "0" + " " * (span[2] - span[1] - 1))
    assert mask_reviewed_identity_literals(SERVICE_PATH, source) == expected


def test_catalog_sites_are_exact_workspace_http_error_operands():
    from common.executive_workspace_contract import error
    from integrations.mastermind_workspace_app.app import _envelope_response

    spans = reviewed_literal_spans(SERVICE_PATH, SOURCE)
    assert tuple(span for span in spans if span[0] >= METHOD.lineno) == STATUS_SITES
    assert any(isinstance(node, ast.ImportFrom)
               and node.module == "common.executive_workspace_contract"
               and any(alias.name == "error" and alias.asname == "workspace_error"
                       for alias in node.names) for node in ast.walk(METHOD))
    for span, reason, status in zip(STATUS_SITES,
                                  ("access_denied", "access_denied", "source_unavailable"),
                                  (403, 403, 503), strict=True):
        calls = [node for node in ast.walk(METHOD)
                 if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                 and node.func.id == "workspace_error" and len(node.args) == 2
                 and not node.keywords and isinstance(node.args[1], ast.Constant)
                 and (node.args[1].lineno, node.args[1].col_offset,
                      node.args[1].end_col_offset, "int") == span]
        assert len(calls) == 1
        assert isinstance(calls[0].args[0], ast.Constant)
        assert calls[0].args[0].value == reason
        assert type(calls[0].args[1].value) is int
        assert calls[0].args[1].value == status
        response = _envelope_response(error(reason, status))
        assert response.status_code == status
        assert response.headers["cache-control"] == "no-store"


def test_catalog_status_mask_requires_the_exact_complete_source():
    spans = reviewed_literal_spans(SERVICE_PATH, SOURCE)
    assert len(spans) == 6
    expected = SOURCE
    for span in reversed(spans):
        expected = _replace_span(expected, span, "0" + " " * (span[2] - span[1] - 1))
    assert mask_reviewed_identity_literals(SERVICE_PATH, SOURCE) == expected
    assert len(expected) == len(SOURCE)
    # A matching method AST in an incomplete file is insufficient when its
    # pre-existing UTF-8 prose requires the full-source pin.
    assert reviewed_literal_spans(SERVICE_PATH, FRAGMENT) == ()
    _assert_catalog_refused(SOURCE + "\n# unrelated source drift\n")


@pytest.mark.parametrize("index", range(3))
@pytest.mark.parametrize("replacement", ["404", "0o623", "peer_uid"])
def test_catalog_literal_value_spelling_or_identity_alias_drift_refuses(index, replacement):
    changed = _replace_span(SOURCE, STATUS_SITES[index], replacement)
    assert changed != SOURCE
    _assert_catalog_refused(changed)


@pytest.mark.parametrize("before,after", [
    ('workspace_error("access_denied", 403)', 'foreign_error("access_denied", 403)'),
    ("error as workspace_error", "other_error as workspace_error"),
    ("app_binding.principal_admission_armed is not True",
     "app_binding.principal_admission_armed is not False"),
    ("or app_binding.principal_facts_factory is not facts_factory", "or False"),
    ("or self._paid_worker_binding_source is not paid_source", "or False"),
    ("if type(owner) is not CooHostProvider:", "if False:"),
    ("class ExecutiveControlService:", "class ForeignService:"),
    ("def _handle_ceo_ingress_connection(", "def _other_ingress_connection("),
])
def test_catalog_callee_admission_owner_or_method_drift_refuses(before, after):
    changed = SOURCE.replace(before, after, 1)
    assert changed != SOURCE
    _assert_catalog_refused(changed)


def test_catalog_duplicate_or_foreign_source_cannot_reuse_the_pin():
    for changed in (SOURCE + "\n" + FRAGMENT,
                    SOURCE.replace(BLOCK, BLOCK + BLOCK, 1),
                    SOURCE.replace(BLOCK, BLOCK + "\n    _handle_ceo_ingress_connection = None\n", 1)):
        _assert_catalog_refused(changed)
    assert reviewed_literal_spans("control_plane/other_service.py", SOURCE) == ()


@pytest.mark.parametrize("suffix,literal", [
    ("\npeer_uid = 471\n", "471"),
    ("\nworker_uid = 403\n", "403"),
    ('\nworker_user = "_mastermind_unreviewed"\n', "_mastermind_unreviewed"),
])
def test_catalog_pin_does_not_hide_adjacent_identities(suffix, literal):
    changed = SOURCE + suffix
    _assert_catalog_refused(changed)
    # Scan only the newly added lines, with the exact complete postimage.
    # Existing unpinned tokens must not make this positive control pass.
    previous_lines = len(SOURCE.splitlines())
    added = suffix.splitlines()
    diff = (f"--- a/{SERVICE_PATH}\n+++ b/{SERVICE_PATH}\n"
            f"@@ -{previous_lines},0 +{previous_lines + 1},{len(added)} @@\n"
            + "\n".join("+" + line for line in added) + "\n")
    assert _scan_added_identity_diff(diff, source_postimages={SERVICE_PATH: changed}) == [literal]


def test_paid_backend_keeps_only_the_three_original_identity_sites():
    source = (ROOT / BACKEND_PATH).read_text()
    assert reviewed_literal_spans(BACKEND_PATH, source) == BACKEND_SITES
    assert [source.splitlines()[line - 1][start:end]
            for line, start, end, _ in BACKEND_SITES] == ["501", "450", "501"]


@pytest.mark.parametrize("index", range(3))
def test_paid_backend_identity_changes_invalidate_the_entire_file_pin(index):
    source = (ROOT / BACKEND_PATH).read_text()
    changed = _replace_span(source, BACKEND_SITES[index], "471")
    assert reviewed_literal_spans(BACKEND_PATH, changed) == ()
    assert "471" in _scan(changed, BACKEND_PATH)

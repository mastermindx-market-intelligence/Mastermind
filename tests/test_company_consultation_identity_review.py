"""Only the reviewed listener method may suppress its three mode literals."""
import ast
from pathlib import Path

import pytest

from tests.executive_company_identity_review import REVIEWED_PATH, REVIEWED_LITERAL_COUNT
from tests.executive_identity_review import reviewed_literal_spans
from tests.test_executive_identity_review import _scan, _replace_span

SOURCE = (Path(__file__).parents[1]/REVIEWED_PATH).read_text()
OWNER = next(n for n in ast.parse(SOURCE).body
             if isinstance(n,ast.ClassDef) and n.name=="ExecutiveControlService")
METHOD = next(n for n in OWNER.body if isinstance(n,ast.AsyncFunctionDef)
              and n.name=="_bind_company_consultation_server")
BLOCK = "".join(SOURCE.splitlines(keepends=True)[METHOD.lineno-1:METHOD.end_lineno])
FRAGMENT = "class ExecutiveControlService:\n"+BLOCK+"\n"


def test_company_review_pins_only_three_mode_sites():
    spans=reviewed_literal_spans(REVIEWED_PATH,SOURCE)
    assert len(spans)==REVIEWED_LITERAL_COUNT==3
    assert all(SOURCE.splitlines()[line-1][start:end]=="0o710" for line,start,end,_ in spans)
    assert len(reviewed_literal_spans(REVIEWED_PATH,FRAGMENT))==3
    assert _scan(FRAGMENT,REVIEWED_PATH)==[]


@pytest.mark.parametrize("index",range(3))
def test_each_company_mode_drift_restores_generic_guard(index):
    spans=reviewed_literal_spans(REVIEWED_PATH,FRAGMENT)
    changed=_replace_span(FRAGMENT,spans[index],"0o711")
    assert reviewed_literal_spans(REVIEWED_PATH,changed)==()
    assert _scan(changed,REVIEWED_PATH)


@pytest.mark.parametrize("change",["body","duplicate_method","duplicate_class","wrong_class","assignment_shadow"])
def test_company_review_rejects_ambiguous_owner_or_method(change):
    if change=="body":
        changed=FRAGMENT.replace('        binding = self._company_consultation_binding',
                                 '        added_uid = 459\n        binding = self._company_consultation_binding')
    elif change=="duplicate_method":
        changed=FRAGMENT+BLOCK
    elif change=="duplicate_class":
        changed=FRAGMENT+"\n"+FRAGMENT
    elif change=="wrong_class":
        changed=FRAGMENT.replace("class ExecutiveControlService:","class DifferentService:",1)
    else:
        changed=FRAGMENT+"    _bind_company_consultation_server = None\n"
    assert reviewed_literal_spans(REVIEWED_PATH,changed)==()
    assert _scan(changed,REVIEWED_PATH)


@pytest.mark.parametrize("suffix",["\nnew_uid=459\n","\nnew_uid=0o710\n"])
def test_unreviewed_company_literals_remain_visible(suffix):
    changed=FRAGMENT+suffix
    assert len(reviewed_literal_spans(REVIEWED_PATH,changed))==3
    assert _scan(changed,REVIEWED_PATH)


def test_company_review_does_not_transfer_to_another_path():
    assert reviewed_literal_spans("control_plane/other_service.py",FRAGMENT)==()
    assert _scan(FRAGMENT,"control_plane/other_service.py")

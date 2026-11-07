"""The frozen helper's display limit needs byte-aware, exact-Constant proof."""
import copy
import hashlib
from pathlib import Path

import pytest

from tests.executive_fabric_release_identity_review import REVIEWED_FILES
from tests.executive_identity_review import reviewed_literal_spans
from tests.test_executive_a2_identity_review import scan

PATH='integrations/session_bridge/mmtask_restore/payload/mmtask'
SOURCE=(Path(__file__).resolve().parents[1]/PATH).read_text()


def test_exact_utf8_constant_returns_character_mask_columns():
    spans=reviewed_literal_spans(PATH,SOURCE)
    assert (214,133,136,'int') in spans
    assert (659,93,96,'int') in spans
    assert scan(SOURCE,PATH)==[]
    # No normalization or transfer to another path/hash.
    assert reviewed_literal_spans('foreign/'+PATH,SOURCE)==()
    assert reviewed_literal_spans(PATH,SOURCE+'\n')==()
    assert reviewed_literal_spans(PATH,SOURCE.replace('—','–'))==()
    assert '457' in scan(SOURCE+'\npeer_uid = 457\n',PATH)


@pytest.mark.parametrize('change',['mid-codepoint','wrong-column','wrong-kind','wrong-spelling','wrong-value'])
def test_invalid_byte_site_never_partially_qualifies_file(monkeypatch,change):
    row=copy.deepcopy(REVIEWED_FILES[PATH]);line,start,end,kind,spelling=row['utf8_sites'][0]
    if change=='mid-codepoint':
        start=len(SOURCE.splitlines()[line-1].split('—')[0].encode())+1;end=start+1
    elif change=='wrong-column':start-=1;end-=1
    elif change=='wrong-kind':kind='str'
    elif change=='wrong-spelling':spelling='0500'
    else:spelling='501'
    row['utf8_sites']=((line,start,end,kind,spelling),)
    monkeypatch.setitem(REVIEWED_FILES,PATH,row)
    assert reviewed_literal_spans(PATH,SOURCE)==()
    assert '500' in scan(SOURCE,PATH) and '400' in scan(SOURCE,PATH)


@pytest.mark.parametrize('suffix,spelling', [('\ncontext = "500"\n','500'),
    ('\ncontext = 5000\n','500'),('\ncontext = 500.0\n','500.0')])
def test_complete_typed_ast_constant_required_even_with_test_rebound_hash(monkeypatch,suffix,spelling):
    source=SOURCE+suffix;lines=source.splitlines();line=len(lines)
    text=lines[-1];start=text.index(spelling);end=start+len(spelling)
    row=copy.deepcopy(REVIEWED_FILES[PATH]);row['sha256']=hashlib.sha256(source.encode()).hexdigest()
    row['utf8_sites']=((line,start,end,'int',spelling),)
    monkeypatch.setitem(REVIEWED_FILES,PATH,row)
    assert reviewed_literal_spans(PATH,source)==()


def test_new_adjacent_identity_is_visible_even_under_test_rebound_hash(monkeypatch):
    source=SOURCE+'\npeer_uid = 457\n'
    row=copy.deepcopy(REVIEWED_FILES[PATH]);row['sha256']=hashlib.sha256(source.encode()).hexdigest()
    monkeypatch.setitem(REVIEWED_FILES,PATH,row)
    assert len(reviewed_literal_spans(PATH,source))==2
    assert scan(source,PATH)==['457']


def test_legacy_ascii_site_does_not_opt_into_unicode(monkeypatch):
    row=copy.deepcopy(REVIEWED_FILES[PATH]);row.pop('utf8_sites')
    row['sites']=((214,133,136,'int','500'),)
    monkeypatch.setitem(REVIEWED_FILES,PATH,row)
    assert reviewed_literal_spans(PATH,SOURCE)==()

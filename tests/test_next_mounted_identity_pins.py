"""Exact metadata for already-reviewed NEXT source; no runtime authority."""
from pathlib import Path
import hashlib
import pytest
from tests.executive_identity_review import mask_reviewed_identity_literals, reviewed_literal_spans
from tests.executive_fabric_release_identity_review import REVIEWED_FILES
ROOT=Path(__file__).parents[1]
PATHS=('app/mastermind_os/src-tauri/src/terminal_session_core.rs','control_plane/workspace_read_service.py')
@pytest.mark.parametrize('path',PATHS)
def test_exact_reviewed_source_and_sites(path):
    source=(ROOT/path).read_text()
    record=REVIEWED_FILES[path]
    assert hashlib.sha256(source.encode()).hexdigest()==record['sha256']
    assert len(reviewed_literal_spans(path,source))==len(record['sites'])
    assert mask_reviewed_identity_literals(path,source)!=source
@pytest.mark.parametrize('path',PATHS)
def test_wrong_path_does_not_mask(path):
    source=(ROOT/path).read_text()
    assert mask_reviewed_identity_literals('unreviewed/'+path,source)==source
@pytest.mark.parametrize('path',PATHS)
def test_unrelated_source_drift_does_not_mask(path):
    source=(ROOT/path).read_text()+'\n'
    assert mask_reviewed_identity_literals(path,source)==source
@pytest.mark.parametrize('path',PATHS)
def test_literal_drift_does_not_mask(path):
    source=(ROOT/path).read_text()
    line,start,end,_,_=REVIEWED_FILES[path]['sites'][0]
    lines=source.splitlines(keepends=True)
    lines[line-1]=lines[line-1][:start]+'499'+lines[line-1][end:]
    changed=''.join(lines)
    assert changed!=source
    assert mask_reviewed_identity_literals(path,changed)==changed

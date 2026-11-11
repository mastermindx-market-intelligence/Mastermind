"""Exact fixture PR/status literals; whole-file drift reopens normal scrutiny."""
from pathlib import Path
import pytest

RECORDS = {
    'app/mastermind_os/src-tauri/src/auth/authorization_continuation.rs': ('66a8938bd1488245d2598be46689801d467ba65250df898e6c61636d64e72e05', ((542, 58, 61, 'int', '600'), (543, 66, 69, 'int', '600'))),
    'integrations/mastermind_workspace_app/native_authorization_identity.py': ('db7f7f1e82de28d99d23f1391d542599180e5ac0daf7b7e689432c73b0c13102', ((72, 25, 28, 'int', '400'), (94, 29, 32, 'int', '400'), (100, 25, 28, 'int', '403'), (108, 29, 32, 'int', '400'), (113, 33, 36, 'int', '400'), (119, 29, 32, 'int', '403'))),
    # 2026-11-09 MMOS composition pin moves: PR #2351 capacity-fabric OS read
    # (commit 3838b8b82) and master #2344 primary/work-entry composition both
    # shifted the same three fixture 503 operands down; the reviewed tokens
    # and columns are byte-identical at their merged positions.
    # 2026-11-10: the T3 attempt-fleet read seam (f6bfac18b) shifted them again
    # to 3878/3883/3887; tokens and columns unchanged.
    # The accepted Paperclip module insertion (master #2395) moves them by one line.
    # 2026-11-11 WO-20 master merge (feat/mmos-v1-integration-merge): both parents'
    # reviewed tokens map byte-identically onto the merged source; only the whole-source
    # digest and line coordinates are requalified. No new literal site is qualified.
    "app/mastermind_os/src-tauri/src/auth.rs": ('8b939d76e742a0f7f0190cc330a60644481a66df1285720ef8a16deb32aac2d9', ((3971, 68, 71, 'int', '503'), (3976, 69, 72, 'int', '503'), (3980, 67, 70, 'int', '503'))),
    "app/mastermind_os/src/fixtures/discovery-correction-owner.json": (
        "363eb680b3a7f982e4fedb8496598b7127ed719c2d1c802831e330bc74ab803f",
        ((163, 18, 21, "int", "401"),)),
}


@pytest.mark.parametrize("path", RECORDS)
def test_exact_literal_sites_do_not_hide_changed_source_or_identity(path):
    import hashlib
    from tests.executive_fabric_release_identity_review import REVIEWED_FILES
    from tests.executive_identity_review import reviewed_literal_spans
    from tests.test_ceo_submit_armed_composition import _scan_added_identity_diff, _d8_frozen_source_diff
    root=Path(__file__).resolve().parents[1];text=(root/path).read_text()
    digest,sites=RECORDS[path]
    assert hashlib.sha256(text.encode()).hexdigest()==digest
    assert REVIEWED_FILES[path]=={"sha256":digest,"sites":sites}
    assert reviewed_literal_spans(path,text)==tuple(row[:4] for row in sites)
    # The full Rust source has nine incumbent findings outside these three
    # reviewed HTTP fixtures. Keep those visible; this record masks none of them.
    incumbent=['430','512','401','403','409','503','503','503','503'] if path == 'app/mastermind_os/src-tauri/src/auth.rs' else []
    assert _scan_added_identity_diff(_d8_frozen_source_diff(path,text),source_postimages={path:text})==incumbent
    lines=text.splitlines();scoped=[f'diff --git a/{path} b/{path}',f'--- a/{path}',f'+++ b/{path}']
    for number in sorted({row[0] for row in sites}):scoped.extend([f'@@ -0,0 +{number},1 @@','+'+lines[number-1]])
    assert _scan_added_identity_diff('\n'.join(scoped),source_postimages={path:text})==[]
    changed=text+"\n"
    assert reviewed_literal_spans(path,changed)==()
    assert _scan_added_identity_diff(_d8_frozen_source_diff(path,changed),source_postimages={path:changed})
    if path.endswith('.rs'):
        changed=text+'\nconst new_peer_uid: u32 = 471;\n'
        assert "471" in _scan_added_identity_diff(_d8_frozen_source_diff(path,changed),source_postimages={path:changed})

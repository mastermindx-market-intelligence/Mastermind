"""The reviewed archive bound stays finite and every source drift stays visible."""
from pathlib import Path
from tests.test_ceo_submit_armed_composition import _scan_added_identity_diff
ROOT=Path(__file__).resolve().parents[1]
PATH='app/mastermind_os/src/projects/archive/project-archive-continuation.ts'

def scan(path, source):
    lines=source.splitlines()
    diff=f'diff --git a/{path} b/{path}\n--- /dev/null\n+++ b/{path}\n@@ -0,0 +1,{len(lines)} @@\n'+'\n'.join('+'+line for line in lines)
    return _scan_added_identity_diff(diff,source_postimages={path:source})

def test_exact_five_hundred_archive_bound_is_not_an_identity_allowance():
    source=(ROOT/PATH).read_text()
    assert 'owner.workRefs.length > 500' in source
    assert scan(PATH,source)==[]
    assert '500' in scan('foreign/'+PATH,source)
    assert '500' in scan(PATH,source+'\n// unrelated source drift\n')
    assert '501' in scan(PATH,source.replace('owner.workRefs.length > 500','owner.workRefs.length > 501'))
    assert '500' in scan(PATH,source+'\nconst peer_uid = 500;\n')

"""Keep the existing identity gate precise without exempting files or paths."""
import pytest
from tests.test_ceo_submit_armed_composition import _scan_added_identity_diff


def scan(source):
    path = "scripts/project_execution_brief.py"
    lines = source.splitlines()
    diff = f"+++ b/{path}\n@@ -0,0 +1,{len(lines)} @@\n" + "\n".join("+" + line for line in lines)
    return _scan_added_identity_diff(diff, source_postimages={path: source})


def test_function_identifier_is_not_an_account_literal():
    assert scan("def is_mastermind_scope(payload):\n    return True\n") == []


def test_explicit_mkdir_mode_is_permission_not_identity():
    assert scan("identity = 'backup'\nbackup_dir.mkdir(parents=True, exist_ok=True, mode=0o700)\n") == []


@pytest.mark.parametrize("source, expected", [
    ("uid = 0o700\n", ["0o700"]),
    ("_mastermind_worker = value\n", ["_mastermind_worker"]),
    ("name = '_mastermind_worker'\n", ["_mastermind_worker"]),
    ("name = 'prefix/_mastermind_worker'\n", ["_mastermind_worker"]),
    ("uid = 501\nbackup_dir.mkdir(mode=0o700)\n", ["501"]),
    ("backup_dir.mkdir(owner=501, mode=0o700)\n", ["501", "0o700"]),
    ("backup_dir.mkdir(mode=0o700); bind_peer(501)\n", ["0o700", "501"]),
    ("peer.mkdir(mode=0o700)\n", ["0o700"]),
])
def test_real_identity_literals_remain_rejected(source, expected):
    assert scan(source) == expected


def test_unreviewed_alias_to_identity_remains_rejected():
    assert scan("candidate = 501\nset_peer(candidate)\n") == ["501"]

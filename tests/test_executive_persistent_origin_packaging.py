"""Exact Git archive/manifest closure, with explicit raw Root-owner facts only."""
import hashlib
import io
import os
from pathlib import Path
import subprocess
import tarfile

from ops.executive_os import release_manifest


def test_committed_helper_is_in_normal_archive_and_manifest(tmp_path, monkeypatch):
    repo = Path(__file__).resolve().parents[1]
    relative = 'ops/executive_os/persistent_origin.py'
    def git(*args):
        return subprocess.check_output(['git', '-C', str(repo), *args])
    head = git('rev-parse', 'HEAD').decode().strip()
    tree = git('rev-parse', 'HEAD^{tree}').decode().strip()
    raw = git('show', 'HEAD:'+relative)
    archive = git('archive', '--format=tar', head, relative)
    with tarfile.open(fileobj=io.BytesIO(archive)) as stored:
        member = stored.getmember(relative)
        assert member.isfile()
        archived = stored.extractfile(member).read()
    assert archived == raw
    stage = tmp_path/'stage'; stage.mkdir(mode=0o755)
    target = stage/relative
    target.parent.mkdir(parents=True, mode=0o755)
    target.write_bytes(archived); target.chmod(0o444)

    # Only ownership observations are synthetic; real walk, mode, ACL,
    # inode, descriptor, byte/hash and manifest producer execute unchanged.
    originals = {name:getattr(os, name) for name in ('stat', 'lstat', 'fstat')}
    def root_facts(call, *args, **kwargs):
        info = call(*args, **kwargs)
        fields = list(info); fields[4:6] = [0, 0]
        extra = {key:getattr(info, key) for key in dir(info)
                 if key.startswith('st_') and key not in
                 {'st_mode', 'st_ino', 'st_dev', 'st_nlink', 'st_uid', 'st_gid', 'st_size'}}
        return os.stat_result(fields, extra)
    for name, call in originals.items():
        monkeypatch.setattr(os, name, lambda *a, _call=call, **k:root_facts(_call, *a, **k))
    manifest = release_manifest._document(stage, head, tree)
    entry, = [item for item in manifest['entries'] if item['path'] == relative]
    assert entry == dict(path=relative, mode=0o444, uid=0, gid=0, type='file',
                         size=len(raw), sha256=hashlib.sha256(raw).hexdigest())
    installer = (repo/'ops/executive_os/install.sh').read_text()
    # The normal producer archives the entire expected commit; there is no
    # static Python allowlist which could omit this newly committed module.
    assert 'archive --format=tar "$EXPECTED_SHA" | (' in installer

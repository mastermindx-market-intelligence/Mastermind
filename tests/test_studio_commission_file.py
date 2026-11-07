import hashlib
import os
from pathlib import Path

import pytest

from integrations.studio_direct_mcp.commission_file import commission_file, CommissionFileRefused, MAX_BYTES

BYTES = b"# Commission\n\nRead the existing workstream contract.\n"


def test_exclusive_same_bytes_reconcile_and_conflict_preservation(tmp_path):
    root = tmp_path.resolve()
    assert commission_file(root) == {"status": "absent"}
    assert not (root / "research").exists()
    assert commission_file(root, BYTES) == {"status": "written", "content_sha256": hashlib.sha256(BYTES).hexdigest()}
    target = root / "research/executive_commissions/COMMISSION.md"
    before = target.stat()
    assert commission_file(root, BYTES)["status"] == "matched"
    assert commission_file(root)["status"] == "matched"
    assert commission_file(root, b"foreign")["status"] == "conflict"
    assert target.read_bytes() == BYTES and target.stat().st_ino == before.st_ino


@pytest.mark.parametrize("part", ["research", "research/executive_commissions", "research/executive_commissions/COMMISSION.md"])
def test_symlink_components_never_write_foreign_target(tmp_path, part):
    root = (tmp_path / "root"); root.mkdir()
    foreign = tmp_path / "foreign"; foreign.mkdir()
    link = root / part
    link.parent.mkdir(parents=True, exist_ok=True)
    link.symlink_to(foreign if part != "research/executive_commissions/COMMISSION.md" else foreign / "target")
    with pytest.raises((OSError, CommissionFileRefused)):
        commission_file(root.resolve(), BYTES)
    assert list(foreign.iterdir()) == []


def test_workspace_symlink_and_relative_path_refuse(tmp_path):
    target = tmp_path / "actual"; target.mkdir()
    link = tmp_path / "link"; link.symlink_to(target)
    with pytest.raises(OSError):
        commission_file(link.absolute(), BYTES)
    with pytest.raises(CommissionFileRefused):
        commission_file(Path("relative"), BYTES)


def test_hardlinked_file_and_writable_directory_refuse(tmp_path):
    root = tmp_path.resolve()
    commission_file(root, BYTES)
    target = root / "research/executive_commissions/COMMISSION.md"
    os.link(target, root / "second")
    with pytest.raises(CommissionFileRefused):
        commission_file(root, BYTES)
    os.unlink(root / "second")
    os.chmod(target.parent, 0o777)
    try:
        with pytest.raises(CommissionFileRefused):
            commission_file(root, BYTES)
    finally:
        os.chmod(target.parent, 0o700)


@pytest.mark.parametrize("content", [b"", b"x\0y", b"\xff", "text", b"x" * (MAX_BYTES + 1)], ids=["empty", "nul", "non-utf8", "non-bytes", "oversize"])
def test_invalid_content_zero_filesystem_effect(tmp_path, content):
    before = set(tmp_path.iterdir())
    with pytest.raises(CommissionFileRefused):
        commission_file(tmp_path.resolve(), content)
    assert set(tmp_path.iterdir()) == before


def test_fifo_is_refused_without_blocking(tmp_path):
    root = tmp_path.resolve()
    parent = root / "research/executive_commissions"; parent.mkdir(parents=True)
    os.mkfifo(parent / "COMMISSION.md", 0o600)
    with pytest.raises(CommissionFileRefused):
        commission_file(root)

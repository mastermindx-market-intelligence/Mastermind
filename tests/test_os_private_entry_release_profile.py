"""Strict 12/14-file private-entry profiles; no wildcard/optional admission.

The legacy 3/9/11/13 profiles stay intact. This exercises the incumbent
manifest builder, not a mock release permission or simulated installation.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from integrations.mastermind_executive_app.os_assets import (
    OS_ASSET_PROFILE_FILE_COUNTS,
    os_asset_mimes,
)
from ops.executive_os.executive_mcp_entry import build_os_asset_manifest


BASE = (
    "index.html",
    "assets/index-ABC_1.css",
    "assets/index-ABC_1.js",
)
NOIR = (
    "assets/atelier-office-ABC_1.jpg",
    "assets/Manrope-Variable-ABC_1.ttf",
    "assets/Inter-Variable-ABC_1.woff2",
)
LICENSES = (
    "licenses/fonts/Inter-OFL.txt",
    "licenses/fonts/Manrope-OFL.txt",
    "licenses/fonts/Manrope-FONTLOG.txt",
)
NOTICES = (
    "third-party/deepseek-client-dependency-NOTICES.txt",
    "third-party/deepseek-harness-LICENSE.txt",
)
PRIVATE_ENTRY = "assets/private-entry-ABC_1.jpg"
RICH_CLIENT = (
    "assets/SourceMarkdown-ABC_1.js",
    "assets/SourceMarkdown-ABC_1.css",
)

PROFILE3 = BASE
PROFILE9 = BASE + NOIR + LICENSES
PROFILE11 = PROFILE9 + NOTICES
PROFILE12 = PROFILE11 + (PRIVATE_ENTRY,)
PROFILE13 = PROFILE11 + RICH_CLIENT
PROFILE14 = PROFILE13 + (PRIVATE_ENTRY,)


def _fixture_source(tmp_path: Path, names: tuple[str, ...]) -> Path:
    root = tmp_path / "app/mastermind_os/dist"
    for name in names:
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        if name == "index.html":
            target.write_text(
                '<script src="/os/assets/index-ABC_1.js"></script>'
                '<link href="/os/assets/index-ABC_1.css">',
                encoding="utf-8",
            )
        else:
            target.write_bytes(b"fixture bytes for " + name.encode("ascii"))
    return tmp_path


@pytest.mark.parametrize("names", [PROFILE3, PROFILE9, PROFILE11, PROFILE12, PROFILE13, PROFILE14])
def test_existing_closed_asset_layouts_remain_qualified(names):
    assert OS_ASSET_PROFILE_FILE_COUNTS == (3, 9, 11, 12, 13, 14)
    mimes = os_asset_mimes(names)
    assert len(mimes) == len(names)
    assert set(mimes) == set(names)
    assert mimes["index.html"] == "text/html; charset=utf-8"
    assert mimes["assets/index-ABC_1.js"] == "text/javascript; charset=utf-8"
    assert mimes["assets/index-ABC_1.css"] == "text/css; charset=utf-8"


def test_exact_current_private_entry_release_has_sealed_manifest(tmp_path):
    root = _fixture_source(tmp_path, PROFILE12)
    manifest = build_os_asset_manifest(root)
    assert manifest["schema"]
    assert len(manifest["files"]) == 12
    rows = {row["path"]: row for row in manifest["files"]}
    assert set(rows) == set(PROFILE12)
    private = (root / "app/mastermind_os/dist" / PRIVATE_ENTRY).read_bytes()
    assert rows[PRIVATE_ENTRY] == {
        "path": PRIVATE_ENTRY,
        "byte_count": len(private),
        "sha256": hashlib.sha256(private).hexdigest(),
        "mime": "image/jpeg",
    }
    assert not any("SourceMarkdown" in name for name in rows)


@pytest.mark.parametrize(
    "names",
    [
        PROFILE12 + ("assets/unapproved-ABC.js",),
        PROFILE12 + (PRIVATE_ENTRY,),
        PROFILE12 + ("assets/SourceMarkdown-ABC_1.js",),
        PROFILE11 + ("assets/private-entry-ABC_1.png",),
        PROFILE11 + ("assets/private-entry-ABC_1.svg",),
        PROFILE11 + ("assets/private-entry-ABC_1.jpeg",),
        PROFILE11 + ("assets/private-entry-ABC_1.jpg/../../.env",),
        PROFILE11 + (None,),
        PROFILE11 + ("../private-entry-ABC_1.jpg",),
        PROFILE11 + ("assets/SourceMarkdown-ABC_1.js",),
        PROFILE9 + ("third-party/deepseek-harness-LICENSE.txt",),
    ],
)
def test_unapproved_or_partial_asset_profiles_fail_closed(names):
    with pytest.raises(ValueError, match="fixed OS asset set required"):
        os_asset_mimes(names)


def test_unauthorized_directory_or_html_reference_refuses_manifest(tmp_path):
    source = _fixture_source(tmp_path, PROFILE12)
    dist = source / "app/mastermind_os/dist"
    (dist / "unapproved").mkdir()
    with pytest.raises(ValueError, match="OS asset directory differs"):
        build_os_asset_manifest(source)
    (dist / "unapproved").rmdir()
    index = dist / "index.html"
    index.write_text('<script src="https://other.example/unapproved.js"></script>')
    with pytest.raises(ValueError, match="OS index asset references differ"):
        build_os_asset_manifest(source)


def test_private_entry_symlink_is_never_a_release_asset(tmp_path):
    source = _fixture_source(tmp_path, PROFILE12)
    private = source / "app/mastermind_os/dist" / PRIVATE_ENTRY
    private.unlink()
    private.symlink_to(source / "app/mastermind_os/dist/assets/index-ABC_1.js")
    with pytest.raises(ValueError, match="OS assets cannot be symlinks"):
        build_os_asset_manifest(source)

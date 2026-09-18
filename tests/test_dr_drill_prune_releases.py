"""Tests for scripts/dr_drill_prune_releases.py (adversarial review M10).

Stubs the module's own `_request` HTTP seam -- zero real network calls.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]


def _load_module():
    spec = importlib.util.spec_from_file_location("dr_drill_prune_releases", _ROOT / "scripts" / "dr_drill_prune_releases.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _FakeReleaseStore:
    def __init__(self, releases: list[dict]) -> None:
        self.releases = {r["id"]: dict(r) for r in releases}
        self.deleted_ids: list[int] = []

    def request(self, method: str, url: str, *, token: str, timeout: float = 30.0) -> tuple[int, bytes]:
        assert token == "test-token"
        if method == "GET" and "/releases?" in url:
            import urllib.parse as _urlparse

            query = dict(_urlparse.parse_qsl(_urlparse.urlparse(url).query))
            page = int(query.get("page", "1"))
            per_page = int(query.get("per_page", "30"))
            ordered = list(self.releases.values())
            start = (page - 1) * per_page
            page_items = ordered[start : start + per_page]
            return 200, json.dumps(page_items).encode("utf-8")
        if method == "DELETE" and "/releases/" in url:
            release_id = int(url.rsplit("/releases/", 1)[1])
            if release_id in self.releases:
                del self.releases[release_id]
                self.deleted_ids.append(release_id)
                return 204, b""
            return 404, b'{"message":"Not Found"}'
        raise AssertionError(f"unexpected request: {method} {url}")


def _drill_release(release_id: int, *, created_at: str, draft: bool = True, tag_prefix: str = "dr-export/") -> dict:
    return {"id": release_id, "tag_name": f"{tag_prefix}{created_at}-{release_id:032x}", "created_at": created_at, "draft": draft}


def test_prune_keeps_newest_n_and_deletes_the_rest(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load_module()
    releases = [_drill_release(i, created_at=f"2026-01-{i:02d}T00:00:00Z") for i in range(1, 13)]  # 12 drill releases
    store = _FakeReleaseStore(releases)
    monkeypatch.setattr(module, "_request", store.request)

    deleted = module.prune("https://api.github.com", "acme/vault", "test-token", tag_prefix="dr-export/", keep=8)
    assert len(deleted) == 4  # 12 - 8
    assert all(item["deleted"] for item in deleted)
    assert len(store.releases) == 8
    # The 8 SURVIVING releases are the newest 8 by created_at.
    surviving_days = sorted(int(r["created_at"][8:10]) for r in store.releases.values())
    assert surviving_days == [5, 6, 7, 8, 9, 10, 11, 12]


def test_prune_never_touches_a_non_draft_release(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load_module()
    releases = [_drill_release(i, created_at=f"2026-01-{i:02d}T00:00:00Z") for i in range(1, 11)]
    # Production/vault release: non-draft, would otherwise be the OLDEST and
    # first in line for pruning by created_at alone.
    releases.append({"id": 999, "tag_name": "dr-export/2025-12-01-prod", "created_at": "2025-12-01T00:00:00Z", "draft": False})
    store = _FakeReleaseStore(releases)
    monkeypatch.setattr(module, "_request", store.request)

    module.prune("https://api.github.com", "acme/vault", "test-token", tag_prefix="dr-export/", keep=8)
    assert 999 in store.releases  # never deleted
    assert store.releases[999]["draft"] is False


def test_prune_never_touches_a_release_outside_the_tag_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load_module()
    releases = [_drill_release(i, created_at=f"2026-01-{i:02d}T00:00:00Z") for i in range(1, 11)]
    releases.append({"id": 888, "tag_name": "some-other-team/unrelated-draft", "created_at": "2025-01-01T00:00:00Z", "draft": True})
    store = _FakeReleaseStore(releases)
    monkeypatch.setattr(module, "_request", store.request)

    module.prune("https://api.github.com", "acme/vault", "test-token", tag_prefix="dr-export/", keep=8)
    assert 888 in store.releases  # never deleted -- wrong tag prefix


def test_prune_no_op_when_at_or_under_the_keep_count(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load_module()
    releases = [_drill_release(i, created_at=f"2026-01-{i:02d}T00:00:00Z") for i in range(1, 6)]  # only 5
    store = _FakeReleaseStore(releases)
    monkeypatch.setattr(module, "_request", store.request)

    deleted = module.prune("https://api.github.com", "acme/vault", "test-token", tag_prefix="dr-export/", keep=8)
    assert deleted == []
    assert len(store.releases) == 5


def test_prune_cli_exits_zero_and_writes_a_summary(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    module = _load_module()
    releases = [_drill_release(i, created_at=f"2026-01-{i:02d}T00:00:00Z") for i in range(1, 13)]
    store = _FakeReleaseStore(releases)
    monkeypatch.setattr(module, "_request", store.request)
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")

    summary_path = tmp_path / "summary.md"
    rc = module.main(["--repo", "acme/vault", "--keep", "8", "--summary-out", str(summary_path)])
    assert rc == 0
    assert summary_path.exists()
    text = summary_path.read_text(encoding="utf-8")
    assert "drill release pruning" in text
    assert text.count("| dr-export/") == 4


def test_prune_cli_requires_the_credential_env_var(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    module = _load_module()
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    rc = module.main(["--repo", "acme/vault", "--keep", "8"])
    assert rc == 65

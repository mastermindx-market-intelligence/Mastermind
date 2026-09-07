from __future__ import annotations

from pathlib import Path

import pytest

from integrations.notion_knowledge_surface.bootstrap import (
    AmbiguousChildError,
    NotionClient,
    NotionEffectUnknown,
    apply_workspace,
    build_plan,
    load_manifest,
)

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "config" / "notion_knowledge_surface_n0.json"
PARENT = "11111111-1111-4111-8111-111111111111"


def _block(kind: str, title: str, object_id: str) -> dict:
    block_type = "child_page" if kind == "page" else "child_database"
    return {"id": object_id, "type": block_type, block_type: {"title": title}}


class FakeClient:
    def __init__(self, *, effect_unknown_key: str | None = None):
        self.blocks: list[dict] = []
        self.created: list[str] = []
        self.effect_unknown_key = effect_unknown_key
        self._unknown_fired = False

    def retrieve_page(self, page_id: str) -> dict:
        return {"object": "page", "id": page_id, "in_trash": False}

    def list_children(self, parent_page_id: str) -> list[dict]:
        assert parent_page_id == PARENT
        return list(self.blocks)

    def create_page(self, parent_page_id: str, title: str) -> dict:
        return self._create("page", title)

    def create_database(self, parent_page_id: str, title: str, properties: dict) -> dict:
        assert properties
        return self._create("database", title)

    def _create(self, kind: str, title: str) -> dict:
        object_id = f"00000000-0000-4000-8000-{len(self.blocks) + 1:012d}"
        self.blocks.append(_block(kind, title, object_id))
        self.created.append(title)
        if self.effect_unknown_key == title and not self._unknown_fired:
            self._unknown_fired = True
            raise NotionEffectUnknown("simulated lost response after effect")
        return {"id": object_id}


def test_manifest_offline_plan_is_exact_eight_creates() -> None:
    manifest = load_manifest(MANIFEST)
    plan = build_plan(manifest, [])
    assert len(plan) == 8
    assert [item.action for item in plan] == ["create"] * 8
    assert [item.title for item in plan] == [
        child["title"] for child in manifest["children"]
    ]
    assert any(item.title == "05 — Operating Manual" for item in plan)


def test_exact_child_reuses_but_wrong_type_does_not() -> None:
    manifest = load_manifest(MANIFEST)
    target = manifest["children"][1]
    blocks = [
        _block(
            target["kind"],
            target["title"],
            "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        ),
        _block("page", target["title"], "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"),
    ]
    plan = build_plan(manifest, blocks)
    item = next(item for item in plan if item.key == target["key"])
    assert item.action == "reuse"
    assert item.object_id == "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"


def test_duplicate_exact_children_refuse() -> None:
    manifest = load_manifest(MANIFEST)
    target = manifest["children"][0]
    blocks = [
        _block(
            target["kind"],
            target["title"],
            "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        ),
        _block(
            target["kind"],
            target["title"],
            "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
        ),
    ]
    with pytest.raises(AmbiguousChildError):
        build_plan(manifest, blocks)


def test_apply_is_idempotent_on_second_run() -> None:
    manifest = load_manifest(MANIFEST)
    client = FakeClient()
    first = apply_workspace(client, PARENT, manifest)
    assert sum(item.action == "created" for item in first) == 8
    created_after_first = list(client.created)

    second = apply_workspace(client, PARENT, manifest)
    assert all(item.action == "reuse" for item in second)
    assert client.created == created_after_first


def test_effect_unknown_reconciles_without_blind_retry() -> None:
    manifest = load_manifest(MANIFEST)
    target_title = manifest["children"][0]["title"]
    client = FakeClient(effect_unknown_key=target_title)

    result = apply_workspace(client, PARENT, manifest)

    target = next(item for item in result if item.title == target_title)
    assert target.action == "reconciled"
    assert client.created.count(target_title) == 1


def test_create_page_uses_page_child_title_shape() -> None:
    client = NotionClient("not-a-real-token")
    captured: dict = {}

    def fake_request(method, path, payload=None, *, mutating=False):
        captured.update(
            method=method,
            path=path,
            payload=payload,
            mutating=mutating,
        )
        return {"id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"}

    client._request = fake_request  # type: ignore[method-assign]
    client.create_page(PARENT, "05 — Operating Manual")

    assert captured["method"] == "POST"
    assert captured["path"] == "/pages"
    assert captured["mutating"] is True
    assert captured["payload"]["parent"] == {"type": "page_id", "page_id": PARENT}
    assert captured["payload"]["properties"] == {
        "title": [
            {"type": "text", "text": {"content": "05 — Operating Manual"}}
        ]
    }


def test_create_database_uses_initial_data_source_schema() -> None:
    client = NotionClient("not-a-real-token")
    captured: dict = {}

    def fake_request(method, path, payload=None, *, mutating=False):
        captured.update(
            method=method,
            path=path,
            payload=payload,
            mutating=mutating,
        )
        return {"id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"}

    client._request = fake_request  # type: ignore[method-assign]
    properties = {"Name": {"title": {}}, "Canonical ID": {"rich_text": {}}}
    client.create_database(PARENT, "01 — Programs", properties)

    assert captured["method"] == "POST"
    assert captured["path"] == "/databases"
    assert captured["mutating"] is True
    assert captured["payload"]["is_inline"] is False
    assert captured["payload"]["initial_data_source"] == {"properties": properties}

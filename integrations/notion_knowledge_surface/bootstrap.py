"""Deterministic N0 Notion workspace bootstrap.

Default behavior is planning/read-only. Creation requires an explicit caller choice.
No Notion object created here owns canonical Mastermind state.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

NOTION_VERSION = "2026-03-11"
API_BASE = "https://api.notion.com/v1"
MANIFEST_SCHEMA = "mastermind.notion_knowledge_surface_n0.v1"
EXPECTED_CHILD_COUNT = 8
VALID_KINDS = {"page", "database"}


class BootstrapError(RuntimeError):
    """Base fail-closed bootstrap error."""


class ManifestError(BootstrapError):
    pass


class AmbiguousChildError(BootstrapError):
    pass


class NotionAPIError(BootstrapError):
    pass


class NotionEffectUnknown(BootstrapError):
    """A mutating request may have reached Notion but no response proved its effect."""


@dataclass(frozen=True)
class PlanItem:
    key: str
    kind: str
    title: str
    action: str
    object_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "kind": self.kind,
            "title": self.title,
            "action": self.action,
            "object_id": self.object_id,
        }


def _normalized_id(value: str) -> str:
    return value.replace("-", "").lower()


def load_manifest(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        manifest = json.load(handle)
    validate_manifest(manifest)
    return manifest


def validate_manifest(manifest: Mapping[str, Any]) -> None:
    if manifest.get("schema") != MANIFEST_SCHEMA:
        raise ManifestError("unexpected manifest schema")
    if manifest.get("notion_version") != NOTION_VERSION:
        raise ManifestError("manifest Notion version is not the reviewed version")
    children = manifest.get("children")
    if not isinstance(children, list) or len(children) != EXPECTED_CHILD_COUNT:
        raise ManifestError(f"N0 manifest must contain exactly {EXPECTED_CHILD_COUNT} children")
    keys: set[str] = set()
    titles: set[str] = set()
    for child in children:
        if not isinstance(child, Mapping):
            raise ManifestError("child entries must be objects")
        key = child.get("key")
        title = child.get("title")
        kind = child.get("kind")
        if not isinstance(key, str) or not key or key in keys:
            raise ManifestError("child keys must be unique non-empty strings")
        if not isinstance(title, str) or not title or title in titles:
            raise ManifestError("child titles must be unique non-empty strings")
        if kind not in VALID_KINDS:
            raise ManifestError(f"unsupported child kind for {key!r}")
        if kind == "database":
            properties = child.get("properties")
            if not isinstance(properties, Mapping):
                raise ManifestError(f"database {key!r} requires properties")
            title_properties = [
                name
                for name, spec in properties.items()
                if isinstance(spec, Mapping) and "title" in spec
            ]
            if len(title_properties) != 1:
                raise ManifestError(f"database {key!r} must have exactly one title property")
        keys.add(key)
        titles.add(title)


def _block_identity(block: Mapping[str, Any]) -> tuple[str, str, str] | None:
    block_type = block.get("type")
    if block_type == "child_page":
        payload = block.get("child_page") or {}
        return "page", str(payload.get("title", "")), str(block.get("id", ""))
    if block_type == "child_database":
        payload = block.get("child_database") or {}
        return "database", str(payload.get("title", "")), str(block.get("id", ""))
    return None


def build_plan(
    manifest: Mapping[str, Any], existing_blocks: Iterable[Mapping[str, Any]]
) -> list[PlanItem]:
    validate_manifest(manifest)
    by_identity: dict[tuple[str, str], list[str]] = {}
    for block in existing_blocks:
        identity = _block_identity(block)
        if identity is None:
            continue
        kind, title, object_id = identity
        by_identity.setdefault((kind, title), []).append(object_id)

    plan: list[PlanItem] = []
    for child in manifest["children"]:
        key = child["key"]
        kind = child["kind"]
        title = child["title"]
        matches = by_identity.get((kind, title), [])
        if len(matches) > 1:
            raise AmbiguousChildError(f"multiple exact {kind} children named {title!r}")
        if matches:
            plan.append(PlanItem(key, kind, title, "reuse", matches[0]))
        else:
            plan.append(PlanItem(key, kind, title, "create", None))
    return plan


class NotionClient:
    """Minimal reviewed REST client; token is kept only in process memory."""

    def __init__(
        self,
        token: str,
        *,
        timeout: float = 20.0,
        sleeper: Callable[[float], None] = time.sleep,
    ):
        if not token:
            raise BootstrapError("Notion token is required")
        self._token = token
        self._timeout = timeout
        self._sleeper = sleeper

    def _request(
        self,
        method: str,
        path: str,
        payload: Mapping[str, Any] | None = None,
        *,
        mutating: bool = False,
    ) -> dict[str, Any]:
        body = (
            None
            if payload is None
            else json.dumps(payload, separators=(",", ":")).encode("utf-8")
        )
        attempts = 1 if mutating else 2
        for attempt in range(attempts):
            request = urllib.request.Request(
                API_BASE + path,
                data=body,
                method=method,
                headers={
                    "Authorization": f"Bearer {self._token}",
                    "Content-Type": "application/json",
                    "Notion-Version": NOTION_VERSION,
                },
            )
            try:
                with urllib.request.urlopen(request, timeout=self._timeout) as response:
                    raw = response.read()
            except urllib.error.HTTPError as exc:
                raw_error = exc.read().decode("utf-8", errors="replace")
                if exc.code == 429 and not mutating and attempt + 1 < attempts:
                    retry_after = min(
                        float(exc.headers.get("Retry-After", "1") or "1"), 5.0
                    )
                    self._sleeper(max(retry_after, 0.0))
                    continue
                raise NotionAPIError(
                    f"Notion HTTP {exc.code}: {raw_error[:500]}"
                ) from exc
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                if mutating:
                    raise NotionEffectUnknown(
                        f"mutating Notion request has unknown effect: {exc}"
                    ) from exc
                raise NotionAPIError(f"Notion transport error: {exc}") from exc
            try:
                decoded = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                if mutating:
                    raise NotionEffectUnknown(
                        "mutating Notion response was not valid JSON"
                    ) from exc
                raise NotionAPIError("Notion response was not valid JSON") from exc
            if not isinstance(decoded, dict):
                if mutating:
                    raise NotionEffectUnknown(
                        "mutating Notion response had an unexpected shape"
                    )
                raise NotionAPIError("Notion response had an unexpected shape")
            return decoded
        raise AssertionError("unreachable")

    def retrieve_page(self, page_id: str) -> dict[str, Any]:
        return self._request("GET", f"/pages/{urllib.parse.quote(page_id)}")

    def list_children(self, parent_page_id: str) -> list[dict[str, Any]]:
        blocks: list[dict[str, Any]] = []
        cursor: str | None = None
        while True:
            query = {"page_size": "100"}
            if cursor:
                query["start_cursor"] = cursor
            path = (
                f"/blocks/{urllib.parse.quote(parent_page_id)}/children?"
                f"{urllib.parse.urlencode(query)}"
            )
            response = self._request("GET", path)
            results = response.get("results")
            if not isinstance(results, list):
                raise NotionAPIError("block children response omitted results")
            blocks.extend(item for item in results if isinstance(item, dict))
            if not response.get("has_more"):
                return blocks
            cursor = response.get("next_cursor")
            if not isinstance(cursor, str) or not cursor:
                raise NotionAPIError("paginated block response omitted next_cursor")

    def create_page(self, parent_page_id: str, title: str) -> dict[str, Any]:
        payload = {
            "parent": {"type": "page_id", "page_id": parent_page_id},
            "properties": {
                "title": [
                    {"type": "text", "text": {"content": title}}
                ]
            },
        }
        return self._request("POST", "/pages", payload, mutating=True)

    def create_database(
        self,
        parent_page_id: str,
        title: str,
        properties: Mapping[str, Any],
    ) -> dict[str, Any]:
        payload = {
            "parent": {"type": "page_id", "page_id": parent_page_id},
            "title": [{"type": "text", "text": {"content": title}}],
            "is_inline": False,
            "initial_data_source": {"properties": dict(properties)},
        }
        return self._request("POST", "/databases", payload, mutating=True)


def _prove_parent(client: NotionClient, parent_page_id: str) -> None:
    response = client.retrieve_page(parent_page_id)
    returned_id = response.get("id")
    if not isinstance(returned_id, str) or _normalized_id(returned_id) != _normalized_id(
        parent_page_id
    ):
        raise BootstrapError("Notion parent identity did not round-trip exactly")
    if response.get("in_trash") is True:
        raise BootstrapError("Notion parent page is in trash")


def apply_workspace(
    client: NotionClient,
    parent_page_id: str,
    manifest: Mapping[str, Any],
) -> list[PlanItem]:
    validate_manifest(manifest)
    _prove_parent(client, parent_page_id)
    existing = client.list_children(parent_page_id)
    plan = build_plan(manifest, existing)
    results: list[PlanItem] = []
    child_by_key = {child["key"]: child for child in manifest["children"]}

    for item in plan:
        if item.action == "reuse":
            results.append(item)
            continue
        child = child_by_key[item.key]
        try:
            if item.kind == "page":
                created = client.create_page(parent_page_id, item.title)
            else:
                created = client.create_database(
                    parent_page_id, item.title, child["properties"]
                )
        except NotionEffectUnknown:
            reconciled = build_plan(manifest, client.list_children(parent_page_id))
            exact = next(candidate for candidate in reconciled if candidate.key == item.key)
            if exact.action == "reuse":
                results.append(
                    PlanItem(
                        item.key,
                        item.kind,
                        item.title,
                        "reconciled",
                        exact.object_id,
                    )
                )
                continue
            raise
        object_id = created.get("id")
        if not isinstance(object_id, str) or not object_id:
            raise NotionEffectUnknown(f"create for {item.key!r} returned no object id")
        results.append(PlanItem(item.key, item.kind, item.title, "created", object_id))

    final_plan = build_plan(manifest, client.list_children(parent_page_id))
    if any(item.action != "reuse" for item in final_plan):
        raise BootstrapError(
            f"post-apply reconciliation did not observe all {EXPECTED_CHILD_COUNT} N0 children"
        )
    return results

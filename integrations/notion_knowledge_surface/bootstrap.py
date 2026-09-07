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
SUPPORTED_PROPERTY_TYPES = {"title", "rich_text", "select", "date", "url"}
DEFAULT_MIN_REQUEST_INTERVAL = 0.35
DEFINITIVE_MUTATION_HTTP_ERRORS = {400, 401, 403, 404, 406}


class BootstrapError(RuntimeError):
    """Base fail-closed bootstrap error."""


class ManifestError(BootstrapError):
    pass


class AmbiguousChildError(BootstrapError):
    pass


class SchemaMismatchError(BootstrapError):
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


def _manifest_property_type(spec: Mapping[str, Any]) -> str:
    matches = [key for key in spec if key in SUPPORTED_PROPERTY_TYPES]
    if len(matches) != 1:
        raise ManifestError("each property must declare exactly one supported type")
    return matches[0]


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
            if not isinstance(properties, Mapping) or not properties:
                raise ManifestError(f"database {key!r} requires properties")
            property_types = {
                name: _manifest_property_type(spec)
                for name, spec in properties.items()
                if isinstance(name, str) and isinstance(spec, Mapping)
            }
            if len(property_types) != len(properties):
                raise ManifestError(f"database {key!r} has malformed properties")
            if list(property_types.values()).count("title") != 1:
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
        clock: Callable[[], float] = time.monotonic,
        min_request_interval: float = DEFAULT_MIN_REQUEST_INTERVAL,
    ):
        if not token:
            raise BootstrapError("Notion token is required")
        if min_request_interval < 0:
            raise BootstrapError("min_request_interval cannot be negative")
        self._token = token
        self._timeout = timeout
        self._sleeper = sleeper
        self._clock = clock
        self._min_request_interval = min_request_interval
        self._last_request_started: float | None = None

    def _pace(self) -> None:
        now = self._clock()
        if self._last_request_started is not None:
            delay = self._min_request_interval - (now - self._last_request_started)
            if delay > 0:
                self._sleeper(delay)
                now = self._clock()
        self._last_request_started = now

    @staticmethod
    def _retry_after(headers: Mapping[str, Any]) -> float:
        raw = headers.get("Retry-After", "1")
        try:
            return min(max(float(raw or "1"), 0.0), 5.0)
        except (TypeError, ValueError):
            return 1.0

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
            self._pace()
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
                    self._sleeper(self._retry_after(exc.headers))
                    continue
                if mutating and exc.code not in DEFINITIVE_MUTATION_HTTP_ERRORS:
                    raise NotionEffectUnknown(
                        f"mutating Notion HTTP {exc.code} has unknown effect: {raw_error[:500]}"
                    ) from exc
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

    def retrieve_database(self, database_id: str) -> dict[str, Any]:
        return self._request("GET", f"/databases/{urllib.parse.quote(database_id)}")

    def retrieve_data_source(self, data_source_id: str) -> dict[str, Any]:
        return self._request(
            "GET", f"/data_sources/{urllib.parse.quote(data_source_id)}"
        )

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
                "title": [{"type": "text", "text": {"content": title}}]
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


def _expected_schema(properties: Mapping[str, Any]) -> dict[str, str]:
    return {
        name: _manifest_property_type(spec)
        for name, spec in properties.items()
        if isinstance(name, str) and isinstance(spec, Mapping)
    }


def _prove_database_schema(
    client: NotionClient,
    database_id: str,
    expected_properties: Mapping[str, Any],
) -> None:
    database = client.retrieve_database(database_id)
    returned_id = database.get("id")
    if not isinstance(returned_id, str) or _normalized_id(returned_id) != _normalized_id(
        database_id
    ):
        raise SchemaMismatchError("Notion database identity did not round-trip exactly")
    if database.get("in_trash") is True:
        raise SchemaMismatchError("Notion database is in trash")
    data_sources = database.get("data_sources")
    if not isinstance(data_sources, list) or len(data_sources) != 1:
        raise SchemaMismatchError(
            "N0 database must contain exactly one data source"
        )
    source_id = data_sources[0].get("id") if isinstance(data_sources[0], Mapping) else None
    if not isinstance(source_id, str) or not source_id:
        raise SchemaMismatchError("N0 database data source identity is missing")
    data_source = client.retrieve_data_source(source_id)
    actual_properties = data_source.get("properties")
    if not isinstance(actual_properties, Mapping):
        raise SchemaMismatchError("N0 data source properties are missing")

    expected = _expected_schema(expected_properties)
    actual: dict[str, str] = {}
    for name, spec in actual_properties.items():
        if not isinstance(name, str) or not isinstance(spec, Mapping):
            raise SchemaMismatchError("N0 data source contains malformed properties")
        property_type = spec.get("type")
        if not isinstance(property_type, str):
            raise SchemaMismatchError(
                f"N0 data source property {name!r} has no type"
            )
        actual[name] = property_type
    if actual != expected:
        raise SchemaMismatchError(
            f"N0 database schema mismatch: expected {expected!r}, observed {actual!r}"
        )


def _prove_reused_database_schemas(
    client: NotionClient,
    manifest: Mapping[str, Any],
    plan: Iterable[PlanItem],
) -> None:
    child_by_key = {child["key"]: child for child in manifest["children"]}
    for item in plan:
        if item.kind != "database" or item.action != "reuse":
            continue
        if not item.object_id:
            raise SchemaMismatchError(f"reused database {item.key!r} has no object id")
        child = child_by_key[item.key]
        _prove_database_schema(client, item.object_id, child["properties"])


def apply_workspace(
    client: NotionClient,
    parent_page_id: str,
    manifest: Mapping[str, Any],
) -> list[PlanItem]:
    validate_manifest(manifest)
    _prove_parent(client, parent_page_id)
    existing = client.list_children(parent_page_id)
    plan = build_plan(manifest, existing)
    _prove_reused_database_schemas(client, manifest, plan)

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
    _prove_reused_database_schemas(client, manifest, final_plan)
    return results

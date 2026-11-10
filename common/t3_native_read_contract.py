"""Pure qualification of the existing T3 native read protocol.

Shared by the foreground session client and Executive's incumbent MCP port.
The injected reader retains transport, authentication and native delivery
bookkeeping. These functions own no connection, cursor store or lifecycle.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from typing import Any


class NativeReadUnavailable(RuntimeError):
    """The native owner did not provide complete qualified evidence."""


class NativeReadConflict(NativeReadUnavailable):
    """An observation no longer names the original native identity."""


def qualify_read_page(
    value: Mapping[str, Any], *, thread_id: str, project_id: str | None,
    after_position: int | None, limit: int,
) -> None:
    detail, items = value.get("thread"), value.get("items")
    if (not isinstance(detail, Mapping) or detail.get("threadId") != thread_id
            or project_id is not None and detail.get("projectId") != project_id):
        raise NativeReadConflict("Native observation changed thread/project identity")
    if (type(items) is not list or len(items) > limit
            or type(value.get("hasMore")) is not bool
            or type(value.get("recentRuns")) is not list):
        raise NativeReadUnavailable("Incomplete native observation")
    positions = []
    for item in items:
        if (type(item) is not dict or type(item.get("position")) is not int
                or item["position"] < 0 or type(item.get("textTruncated")) is not bool
                or item.get("text") is not None and type(item["text"]) is not str):
            raise NativeReadUnavailable("Malformed native timeline item")
        positions.append(item["position"])
    if positions != sorted(set(positions)):
        raise NativeReadUnavailable("Native timeline is unordered or duplicated")
    if after_position is not None and positions and positions[0] <= after_position:
        raise NativeReadConflict("Native timeline repeated an already consumed position")
    nxt = value.get("nextPosition")
    if nxt is not None and (type(nxt) is not int or nxt < 0
                            or after_position is not None and nxt <= after_position):
        raise NativeReadUnavailable("Native cursor did not advance")
    if value["hasMore"] and (nxt is None or not positions or nxt < positions[-1]):
        raise NativeReadUnavailable("Native page has no recoverable continuation")


async def read_full_item(
    item: Mapping[str, Any], *, thread_id: str,
    read: Callable[[dict[str, Any]], Awaitable[Mapping[str, Any]]],
    qualify: Callable[[Mapping[str, Any]], None],
    max_chunks: int = 8, max_bytes: int = 32_768,
) -> tuple[str | None, bool]:
    """Expand one original item using only native UTF-16 continuation offsets.

    A size/chunk limit returns explicit incompleteness, never sliced content.
    Native item revision, when supplied, must stay unchanged during expansion.
    """
    if type(max_chunks) is not int or not 1 <= max_chunks <= 16:
        raise ValueError("Invalid max_chunks")
    if (not isinstance(item, Mapping) or type(item.get("text")) is not str
            or item.get("sourceThreadId") != thread_id
            or type(item.get("textTruncated")) is not bool
            or type(item.get("itemId")) is not str or not item["itemId"]):
        raise ValueError("Original exact native text item required")
    item_id, run_id, text = item["itemId"], item.get("runId"), item["text"]
    revision = item.get("updatedAt")
    if len(text.encode("utf-8")) > max_bytes:
        return None, False
    if not item["textTruncated"]:
        return text, True
    offset = item.get("nextTextOffset")
    if type(offset) is not int or offset <= 0:
        raise NativeReadUnavailable("Truncated native text has no continuation offset")
    for _ in range(max_chunks):
        result = await read({"threadId": thread_id, "itemId": item_id,
                             "textOffset": offset, "maxCharsPerItem": 8192, "runLimit": 1})
        qualify(result)
        rows = result["items"]
        if len(rows) != 1:
            raise NativeReadConflict("Original native text item disappeared")
        chunk = rows[0]
        if (chunk.get("itemId") != item_id or chunk.get("runId") != run_id
                or chunk.get("sourceThreadId") != thread_id
                or type(chunk.get("text")) is not str
                or chunk.get("type") != item.get("type")
                or chunk.get("updatedAt") != revision):
            raise NativeReadConflict("Native text expansion changed identity or revision")
        text += chunk["text"]
        if len(text.encode("utf-8")) > max_bytes:
            return None, False
        if chunk["textTruncated"] is False:
            return text, True
        nxt = chunk.get("nextTextOffset")
        if type(nxt) is not int or nxt <= offset:
            raise NativeReadUnavailable("Native text offset did not advance")
        offset = nxt
    return None, False


def qualify_wait(value: Mapping[str, Any], *, thread_id: str, run_id: str,
                 exact_result: bool = True) -> None:
    if (value.get("threadId") != thread_id or value.get("runId") != run_id
            or type(value.get("timedOut")) is not bool
            or type(value.get("status")) is not str):
        raise NativeReadConflict("Native wait no longer identifies the original run")
    result_run = value.get("resultRun")
    if exact_result and result_run is not None and (
            not isinstance(result_run, Mapping) or result_run.get("runId") != run_id
            or result_run.get("status") != value["status"]):
        raise NativeReadConflict("Native final result no longer identifies the original run")

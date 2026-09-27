"""Bounded Paper file focus through the reviewed vendor API, not host control.

Reuses bridge.py's transport, desktop mutex, snapshots and exact schema pin.
The raw vendor open_file accepts URLs and incorrectly labels focus as read-only.
This projection accepts only one bare Paper ULID, treats focus as a write, checks
fresh source context, sends at most one open, and observes the actual active file.
No shell, app launcher, filesystem path, URL, page override or retry owner exists.
Paper must already be running and its current document inspectable.
"""
from __future__ import annotations

import re
import time
import bridge

FILE_ID_RE = re.compile(r"[0-9A-HJKMNP-TV-Z]{26}")
OPERATION_RE = re.compile(r"[A-Za-z0-9_.:-]{1,120}")
SNAPSHOT_RE = re.compile(r"[0-9a-f]{64}")
MAX_OBSERVATIONS = 5


def _file_id(observation: dict | None) -> str | None:
    identity = (observation or {}).get("identity") or {}
    return identity.get("id") if identity.get("kind") == "file-id" else None


def prepare_document(file_id: str, expected_snapshot: str, operation_id: str, *,
                     allow_prepare: bool = False, client=None, lock_root=None,
                     _server_pin=bridge.SUPPORTED_SERVER,
                     _catalog_pin=bridge.SUPPORTED_CATALOG_SHA256,
                     _sleep=time.sleep) -> dict:
    """One opt-in, serialized file-focus operation with no content mutation.

    An operation ID is correlation, not a deduplication token or a write grant.
    A lost/error reply remains EFFECT_UNKNOWN even when post-read sees the target;
    that evidence is available to the caller for same-carrier reconciliation.
    """
    if allow_prepare is not True:
        raise bridge.Refusal("PREPARE_DISABLED")
    if not isinstance(file_id, str) or not FILE_ID_RE.fullmatch(file_id):
        raise bridge.Refusal("FILE_ID_REQUIRED", "Use one exact bare Paper file ID, never a URL or path.")
    if not isinstance(operation_id, str) or not OPERATION_RE.fullmatch(operation_id):
        raise bridge.Refusal("OPERATION_ID_REQUIRED")
    if not isinstance(expected_snapshot, str) or not SNAPSHOT_RE.fullmatch(expected_snapshot):
        raise bridge.Refusal("SNAPSHOT_REQUIRED")
    client = client or bridge.PaperClient(timeout=4)
    with bridge.desktop_lock(lock_root):
        client.initialize()
        catalog = client.catalog()
        schema = bridge.schema_receipt(client, catalog, server_pin=_server_pin, catalog_pin=_catalog_pin)
        before = bridge.snapshot(client)
        if before["snapshot_sha256"] != expected_snapshot:
            raise bridge.Refusal("DOCUMENT_CHANGED", "Inspect the current file before deciding on focus.")
        receipt = {
            "file_id": file_id, "operation_id": operation_id, "before": before,
            "write_schema": schema, "write_qualified": schema["accepted_for_write"],
            "retry_allowed": False, "production_acceptance": False,
            "concurrency_rule": "ONE_WRITER_PER_FILE_ACROSS_HOSTS",
        }
        if _file_id(before) == file_id:
            return dict(receipt, state="PAPER_READY" if schema["accepted_for_write"] else "PAPER_READY_READ_ONLY",
                        already_active=True, open_attempted=False, response_observed=True,
                        after=before, snapshot_sha256=before["snapshot_sha256"])
        if not schema["accepted_for_write"]:
            raise bridge.Refusal("UPSTREAM_SCHEMA_UNREVIEWED", "File focus also requires the reviewed schema pin.")
        if "open_file" not in catalog:
            raise bridge.Refusal("TOOL_NOT_AVAILABLE")

        # Deliberately do not accept vendor URL, route or pageId forms. There is
        # exactly one effect-bearing request. Neither response loss nor timeout
        # leads to another open or to a host-level fallback.
        result = None
        try:
            result = client.call("open_file", {"fileId": file_id})
        except Exception:
            pass
        response_observed = isinstance(result, dict)
        response_ok = response_observed and not result.get("isError")
        after, observation_error = None, None
        for attempt in range(MAX_OBSERVATIONS):
            try:
                # No fileId parameter: observe what is actually active, rather
                # than merely reading the requested target in the background.
                after = bridge.snapshot(client)
            except bridge.Refusal as exc:
                observation_error = exc.code
                break  # An explicit denial is not a reason to keep probing.
            except Exception:
                observation_error = "POST_READ_UNAVAILABLE"
                break
            if _file_id(after) == file_id:
                break
            if attempt + 1 < MAX_OBSERVATIONS:
                _sleep(0.15)
        matched = _file_id(after) == file_id
        ready = bool(response_ok and matched)
        return dict(receipt, state="PAPER_READY" if ready else "EFFECT_UNKNOWN",
                    already_active=False, open_attempted=True,
                    response_observed=response_observed, response_ok=bool(response_ok),
                    target_observed=matched, result=result, after=after,
                    snapshot_sha256=after["snapshot_sha256"] if after else None,
                    observation_error=observation_error,
                    reason=None if ready else ("PREPARE_REPLY_UNCERTAIN" if not response_ok else "TARGET_NOT_OBSERVED"))

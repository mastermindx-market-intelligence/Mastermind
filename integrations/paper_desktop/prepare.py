"""Bounded Paper target preparation through explicit file binding, not host control.

Reuses bridge.py's transport, desktop mutex, target snapshots and exact schema pin.
Paper 0.5.12 can address files directly by fileId even when another file remains
user-active. This projection accepts only one bare Paper ULID, checks fresh source
context, validates the exact target read, and returns its snapshot for a subsequent
explicit-file edit. It never calls raw vendor open_file, shell, app launchers, paths,
URLs, page overrides, or a retry owner. Paper must already be running.
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
    """One opt-in, serialized target-binding operation with no Paper mutation.

    An operation ID is correlation, not a deduplication token or a write grant.
    The returned snapshot belongs to the exact requested file and is the guard for
    the subsequent explicit-file edit; the user's active Paper file need not switch.
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
            "concurrency_rule": "MULTI_WRITER_PER_FILE_TARGET_SCOPED",
        }
        if _file_id(before) == file_id:
            return dict(receipt, state="PAPER_READY" if schema["accepted_for_write"] else "PAPER_READY_READ_ONLY",
                        already_active=True, open_attempted=False, response_observed=True,
                        target_observed=True, target_active=True, target_addressable=True,
                        after=before, snapshot_sha256=before["snapshot_sha256"])

        # Paper 0.5.12 addresses files directly by fileId, including files that are
        # not user-active. Do not use vendor open_file as a focus surrogate: its
        # successful response is not a guarantee that the user's active file changes.
        # Prepare therefore performs only a target-specific read/binding check and
        # returns the target snapshot required by the subsequent explicit-file edit.
        target = bridge.snapshot(client, file_id)
        return dict(receipt,
                    state="PAPER_READY" if schema["accepted_for_write"] else "PAPER_READY_READ_ONLY",
                    already_active=False, open_attempted=False, response_observed=True,
                    response_ok=True, target_observed=True, target_active=False,
                    target_addressable=True, prepare_mode="EXPLICIT_FILE_BINDING",
                    result=None, after=target, snapshot_sha256=target["snapshot_sha256"],
                    observation_error=None, reason=None)

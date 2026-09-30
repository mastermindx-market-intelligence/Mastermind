"""Bounded Paper target preparation through explicit file binding, not host control.

Reuses bridge.py's transport, desktop mutex, target snapshots and exact schema pin.
Reviewed Paper Desktop generations can address files directly by fileId even when another file remains
user-active. This projection accepts only one bare Paper ULID, checks a fresh exact-target
snapshot, validates the target read, and returns its snapshot for a subsequent
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
                     allow_prepare: bool = False, client=None, lock_root=None, execution_binding=None,
                     _server_pin=bridge.SUPPORTED_SERVERS,
                     _catalog_pin=bridge.SUPPORTED_CATALOG_SHA256,
                     _sleep=time.sleep) -> dict:
    """One opt-in, serialized target-binding operation with no Paper mutation.

    An operation ID is correlation, not a deduplication token or a write grant.
    The returned snapshot belongs to the exact requested file and is the guard for
    the subsequent explicit-file edit; the user's active Paper file need not switch.
    """
    execution_binding = bridge.validate_execution_binding(execution_binding)
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
        # Bind and guard the exact requested file first. Another admitted
        # session may change the user's foreground file, and Paper may have no usable
        # default active-file context at all. Neither condition is relevant to an
        # explicit-file operation and must not invalidate this target.
        target = bridge.snapshot(client, file_id, execution_binding=execution_binding)
        if target["snapshot_sha256"] != expected_snapshot:
            raise bridge.Refusal(
                "DOCUMENT_CHANGED",
                "Re-read the exact target file before deciding on a new operation.",
            )
        receipt = {
            "file_id": file_id, "operation_id": operation_id, "before": target,
            "write_schema": schema, "write_qualified": schema["accepted_for_write"],
            "retry_allowed": False, "production_acceptance": False,
            "concurrency_rule": "MULTI_WRITER_PER_FILE_TARGET_SCOPED",
            "same_file_multi_writer_allowed": True,
            "same_page_multi_writer_allowed": True,
            "coordination_scope": "BOARD_ARTBOARD_NODE",
        }

        # Reviewed Paper Desktop generations address files directly by fileId, including files that are
        # not user-active. Do not use vendor open_file as a focus surrogate and do
        # not query unrelated active context merely to qualify this target. Active
        # state is therefore intentionally unknown rather than guessed.
        return dict(receipt,
                    state="PAPER_READY" if schema["accepted_for_write"] else "PAPER_READY_READ_ONLY",
                    already_active=None, open_attempted=False, response_observed=True,
                    response_ok=True, target_observed=True, target_active=None,
                    target_addressable=True, prepare_mode="EXPLICIT_FILE_BINDING",
                    active_context_required=False, result=None, after=target,
                    snapshot_sha256=target["snapshot_sha256"],
                    observation_error=None, reason=None)

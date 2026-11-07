"""Rootless archive sample inside the existing current catalogue/READ permission."""
import asyncio

from common import workspace_project_archive_contract as wire
from common.executive_workspace_contract import error
from control_plane.agentos_project_archive import AgentOsProjectArchiveReader
from control_plane.workspace_read_service import (
    WorkspaceReadService, _qualified, _plan_validity_identity, digest,
    permission_stamp, await_owned,
)


class ProjectArchiveReadAdapter:
    def __init__(self, *, workspace, reader):
        if type(workspace) is not WorkspaceReadService or reader is not None and type(reader) is not AgentOsProjectArchiveReader:
            raise ValueError("SOURCE_UNAVAILABLE")
        self._workspace, self._reader = workspace, reader

    @staticmethod
    def _catalogue(snapshot, cursor=None):
        if not _qualified(snapshot):
            raise ValueError("SOURCE_UNAVAILABLE")
        refs = sorted(wire.work_ref(row["work_ref"]) for row in snapshot.document["work"])
        if len(refs) > 500 or len(set(refs)) != len(refs):
            raise ValueError("SOURCE_UNAVAILABLE")
        macro = snapshot.document.get("sources", {}).get("macro_sha")
        if not wire._hex(macro, 40):
            raise ValueError("SOURCE_UNAVAILABLE")
        document_digest = digest(snapshot.document)
        start = 0
        if cursor is not None:
            wire.page_selection(cursor)
            if cursor["catalogue_digest"] != document_digest or cursor["after_work_ref"] not in refs:
                raise _ArchiveCatalogueChanged()
            start = refs.index(cursor["after_work_ref"]) + 1
        return {"document_digest": document_digest, "macro_sha": macro,
                "work_refs": refs[start:start + wire.MAX_MEMBERS], "qualified_catalogue_count": len(refs)}

    def _read(self, cursor=None):
        owner, reader = self._workspace, self._reader
        cache = owner.cache
        before = cache.snapshot()
        try:
            catalogue = self._catalogue(before, cursor)
        except _ArchiveCatalogueChanged:
            return wire.unavailable("SOURCE_CHANGED")
        if reader is None:
            return wire.unavailable()
        sample = reader.read(work_refs=catalogue["work_refs"], expected_current_macro_sha=catalogue["macro_sha"])
        after = owner.cache.snapshot()
        try:
            after_catalogue = self._catalogue(after, cursor)
        except (ValueError, _ArchiveCatalogueChanged):
            return wire.unavailable("SOURCE_CHANGED")
        if (owner.cache is not cache or self._workspace is not owner or self._reader is not reader
                or after_catalogue != catalogue
                or before.owner is not after.owner or before.instance != after.instance
                or before.publication != after.publication
                or digest(_plan_validity_identity(before.validity)) != digest(_plan_validity_identity(after.validity))
                or digest(before.currentness) != digest(after.currentness)):
            return wire.unavailable("SOURCE_CHANGED")
        return wire.validate_body({"schema": wire.BODY_SCHEMA, "availability": "AVAILABLE",
            "catalogue": catalogue, "sample": sample, "reason_codes": []})

    async def handle_frame(self, frame):
        try:
            wire.validate_read_frame(frame)
        except (TypeError, ValueError):
            return error("invalid_input", 400)
        owner = self._workspace
        authorizer = owner.authorize
        principal = frame["principal"]
        try:
            if authorizer(principal) is not True:
                return error("access_denied", 403)
            stamp = permission_stamp(authorizer, principal)
            if stamp is None:
                return error("access_denied", 403)
        except Exception:
            return error("access_denied", 403)
        task = asyncio.create_task(asyncio.to_thread(self._read, frame.get("selection")))
        try:
            body = await await_owned(task)
        except Exception:
            body = wire.unavailable()
        try:
            if (self._workspace is not owner or owner.authorize is not authorizer
                    or authorizer(principal) is not True or permission_stamp(authorizer, principal) != stamp):
                return error("access_denied", 403)
        except Exception:
            return error("access_denied", 403)
        return {"ok": True, "result": body}


class _ArchiveCatalogueChanged(Exception):
    pass

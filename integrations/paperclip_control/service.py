"""Request-scoped composition over the incumbent Paperclip API.

There is no local cache, replication, queue, retry owner or background worker.
Every invocation uses the existing Workspace principal and one configured company.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from urllib.parse import urlencode

from .contract import (
    COMMAND_SCHEMA, DONOR_REVISION, PAGE_SIZE, SCHEMA, PaperclipError,
    command_request, digest, identifier, project_record, read_selection, timestamp,
)
from .installed import PaperclipWorkspaceBinding
from .runtime_migration import prepare_existing_runtime
from .connections import project_connections


class PaperclipWorkspace:
    def __init__(self, binding: PaperclipWorkspaceBinding, principal, *, authorize, now):
        self.binding, self.principal = binding, principal
        self.authorize, self.now = authorize, now
        self.access = self._check()
        self._token = binding.credential(self.access)

    def _check(self, *, mutate=False):
        try:
            authorized = self.authorize(self.principal) is True and self.principal.expires_at > self.now()
        except Exception:
            authorized = False
        if not authorized:
            raise PaperclipError("COMPANY_ACCESS_DENIED", status=403)
        return self.binding.permission(self.principal, mutate=mutate)

    async def _call(self, method, path, *, body=None):
        mutate = method != "GET"
        access = self._check(mutate=mutate)
        if self.binding.credential(access) != self._token:
            raise PaperclipError("COMPANY_ACCESS_CHANGED", status=403)
        result = await self.binding.client.request(method, path, token=self._token,
            local_operator=access.local_operator, body=body)
        try:
            after = self._check(mutate=mutate)
            if self.binding.credential(after) != self._token:
                raise PaperclipError("COMPANY_ACCESS_CHANGED", status=403)
        except PaperclipError:
            raise PaperclipError("COMPANY_ACCESS_CHANGED", effect="EFFECT_UNKNOWN" if mutate else "NOT_APPLIED", status=403) from None
        return result

    @property
    def company_path(self):
        return "/api/companies/" + self.binding.company_id

    async def _health(self):
        try:
            value = await self._call("GET", "/api/health")
            commit = value.get("commit") if type(value) is dict else None
            return commit if isinstance(commit, str) and len(commit) == 40 else None
        except PaperclipError:
            return None

    async def _company(self):
        raw = await self._call("GET", self.company_path)
        if type(raw) is not dict or identifier(raw.get("id")) != self.binding.company_id:
            raise PaperclipError("SOURCE_SCOPE_MISMATCH")
        return project_record("company", raw, self.binding.company_id)

    async def _owned(self, kind: str, item_id: str):
        route = {"task": "issues", "project": "projects", "routine": "routines", "runtime": "agents"}[kind]
        raw = await self._call("GET", f"/api/{route}/{identifier(item_id)}")
        if type(raw) is not dict or raw.get("companyId") != self.binding.company_id or identifier(raw.get("id")) != item_id:
            raise PaperclipError("SOURCE_SCOPE_MISMATCH")
        return raw

    async def _collection(self, kind, selected):
        offset = selected.get("offset", 0)
        query: dict = {}
        if selected.get("projectId"):
            query["projectId"] = selected["projectId"]
        if kind == "work":
            path = self.company_path + "/issues"
            query.update(limit=PAGE_SIZE + 1, offset=offset, sortField="updated", sortDir="desc")
            if selected.get("status"):
                query["status"] = selected["status"]
        else:
            path = self.company_path + "/" + {"people": "agents"}.get(kind, kind)
            if kind in {"activity", "artifacts"}:
                query["limit"] = PAGE_SIZE if kind == "artifacts" else PAGE_SIZE + 1
            if kind == "artifacts" and selected.get("cursor"):
                query["cursor"] = selected["cursor"]
        if query:
            path += "?" + urlencode(query)
        try:
            raw = await self._call("GET", path)
            cursor = None
            if kind == "artifacts" and type(raw) is dict:
                cursor, raw = raw.get("nextCursor"), raw.get("artifacts")
                if cursor is not None and (not isinstance(cursor, str) or len(cursor) > 2048):
                    raise PaperclipError("SOURCE_RESPONSE_INVALID")
            if type(raw) is not list:
                raise PaperclipError("SOURCE_RESPONSE_INVALID")
            # Work is upstream paged; other documented list APIs return arrays.
            # Activity is a latest-event window, never advertised as full history.
            window = raw if kind in {"work", "artifacts", "activity"} else raw[offset:]
            items = []
            restricted = 0
            for row in window[:PAGE_SIZE]:
                if type(row) is dict and row.get("locked") is True:
                    restricted += 1
                    continue
                items.append(project_record(kind, row, self.binding.company_id,
                    allow_scoped_id=kind == "artifacts"))
            more = len(window) > PAGE_SIZE or cursor is not None
            return {"state": "CURRENT", "items": items, "restrictedCount": restricted,
                    "coverage": "LATEST_WINDOW" if kind == "activity" else "BOUNDED_RESPONSE",
                    "hasMore": more,
                    "nextOffset": offset + PAGE_SIZE if more and kind not in {"artifacts", "activity"} else None,
                    "nextCursor": cursor}
        except PaperclipError as exc:
            if exc.code in {"COMPANY_ACCESS_DENIED", "COMPANY_ACCESS_CHANGED", "COMPANY_BINDING_CHANGED", "SOURCE_SCOPE_MISMATCH"}:
                raise
            return {"state": "UNAVAILABLE", "items": [], "code": exc.code,
                    "coverage": "UNAVAILABLE", "hasMore": False, "nextOffset": None, "nextCursor": None}

    async def _related(self, kind, path, *, parent_key, parent_id):
        try:
            raw = await self._call("GET", path)
            if type(raw) is not list:
                raise PaperclipError("SOURCE_RESPONSE_INVALID")
            items = []
            for row in raw[:PAGE_SIZE]:
                if type(row) is not dict or row.get(parent_key) not in {None, parent_id}:
                    raise PaperclipError("SOURCE_SCOPE_MISMATCH")
                items.append(project_record(kind, row, self.binding.company_id))
            return {"state": "CURRENT", "items": items, "coverage": "BOUNDED_RESPONSE",
                    "hasMore": len(raw) > PAGE_SIZE, "nextOffset": None, "nextCursor": None}
        except PaperclipError as exc:
            if exc.code in {"COMPANY_ACCESS_DENIED", "COMPANY_ACCESS_CHANGED", "COMPANY_BINDING_CHANGED", "SOURCE_SCOPE_MISMATCH"}:
                raise
            return {"state": "UNAVAILABLE", "items": [], "code": exc.code,
                    "coverage": "UNAVAILABLE", "hasMore": False, "nextOffset": None, "nextCursor": None}

    def _request_key(self, request_id):
        return "mmos-paperclip-" + digest({"scope": self.binding.scope(self.principal), "requestId": identifier(request_id)})

    async def _receipt(self, request_id):
        key = self._request_key(request_id)
        marker = "<!-- " + key + " -->"
        raw = await self._call("GET", self.company_path + "/issues?" + urlencode({"q": key, "limit": PAGE_SIZE + 1}))
        if type(raw) is not list:
            raise PaperclipError("SOURCE_RESPONSE_INVALID")
        candidates = [row for row in raw if type(row) is dict and row.get("companyId") == self.binding.company_id
                      and marker in str(row.get("description", ""))]
        # An editable marker is only a discovery aid. It cannot prove the native
        # idempotency ledger accepted this original request. No absence => retry.
        confirmed = [row for row in candidates if row.get("idempotencyKey") == key]
        return {"requestId": request_id, "state": "SAVED" if len(confirmed) == 1 else "EFFECT_UNKNOWN",
                "code": "SOURCE_RECEIPT_CONFIRMED" if len(confirmed) == 1 else "ORIGINAL_SOURCE_RECEIPT_REQUIRED",
                "item": project_record("work", confirmed[0], self.binding.company_id) if len(confirmed) == 1 else None,
                "candidates": [project_record("work", row, self.binding.company_id) for row in candidates[:5]],
                "retryAllowed": False}

    async def read(self, raw_selection):
        selected = read_selection(raw_selection)
        company, observed_revision = await asyncio.gather(self._company(), self._health())
        result = {"schema": SCHEMA, "state": "CURRENT", "view": selected["view"],
                  "company": company, "bindingRevision": self.binding.revision,
                  "scopeKey": self.binding.scope(self.principal),
                  "observedAt": datetime.fromtimestamp(self.now(), timezone.utc).isoformat().replace("+00:00", "Z"),
                  "sourceRevision": observed_revision, "qualifiedRevision": self.binding.source_revision,
                  "capabilities": [], "collections": {}, "item": None,
                  "ownership": {"work": self.binding.work_owner, "wake": self.binding.wake_owner,
                                "runtime": "hermes", "admission": "executive", "routing": "capacity"},
                  "runtimeBindings": [], "projectBindings": []}
        if observed_revision == DONOR_REVISION:
            try:
                self._check(mutate=True)
                result["capabilities"] = ["create_backlog"]
            except PaperclipError:
                pass
        view = selected["view"]
        visible_projects = set()
        visible_agents = set()
        if "projectId" in selected:
            await self._owned("project", selected["projectId"])
            visible_projects.add(selected["projectId"])
        if view == "overview":
            names = ("people", "projects", "goals", "work", "routines")
            collections = await asyncio.gather(*(self._collection(name, {}) for name in names))
            result["collections"] = dict(zip(names, collections))
        elif view == "task":
            item = await self._owned("task", selected["itemId"])
            result["item"] = project_record("work", item, self.binding.company_id)
            relations = (("comments", "comments"), ("products", "work-products"), ("executions", "runs"))
            related = await asyncio.gather(*(self._related(kind, "/api/issues/" + selected["itemId"] + "/" + route,
                parent_key="issueId", parent_id=selected["itemId"]) for kind, route in relations))
            result["collections"] = dict(zip((kind for kind, _ in relations), related))
            project_id = item.get("projectId")
            if project_id is not None and any(project == project_id for project, _ in self.binding.project_bindings):
                try:
                    await self._owned("project", identifier(project_id))
                    visible_projects.add(project_id)
                except PaperclipError as exc:
                    if exc.code in {"COMPANY_ACCESS_DENIED", "COMPANY_ACCESS_CHANGED", "COMPANY_BINDING_CHANGED", "SOURCE_SCOPE_MISMATCH"}:
                        raise
                    # A readable task does not imply permission to its project.
                    # Keep this exact task available without exposing the OS join.

        elif view == "routine":
            item = await self._owned("routine", selected["itemId"])
            result["item"] = project_record("routines", item, self.binding.company_id)
            names = ("runs", "revisions")
            related = await asyncio.gather(*(self._related(name, "/api/routines/" + selected["itemId"] + "/" + name,
                parent_key="routineId", parent_id=selected["itemId"]) for name in names))
            result["collections"] = dict(zip(names, related))
        elif view == "runtime":
            item = await self._owned("runtime", selected["itemId"])
            result["item"] = project_record("people", item, self.binding.company_id)
            visible_agents.add(selected["itemId"])
            binding = next((entry for entry in self.binding.hermes_bindings if entry.agent_id == selected["itemId"]), None)
            result["migration"] = prepare_existing_runtime(item, company_id=self.binding.company_id, binding=binding,
                work_owner=self.binding.work_owner, wake_owner=self.binding.wake_owner)
        elif view == "receipt":
            result["receipt"] = await self._receipt(selected["requestId"])
        else:
            result["collections"][view] = await self._collection(view, selected)
        for kind, visible in (("people", visible_agents), ("projects", visible_projects)):
            collection = result["collections"].get(kind)
            if collection is not None and collection["state"] == "CURRENT":
                visible.update(row["id"] for row in collection["items"])
        result["runtimeBindings"] = [entry.public() for entry in self.binding.hermes_bindings if entry.agent_id in visible_agents]
        result["projectBindings"] = [{"projectId": project, "workRef": work}
            for project, work in self.binding.project_bindings if project in visible_projects]
        if any(collection["state"] != "CURRENT" for collection in result["collections"].values()):
            result["state"] = "PARTIAL"
        result["connections"] = project_connections(result)
        self._check()
        return result

    async def command(self, raw_request):
        request = command_request(raw_request)
        self._check(mutate=True)
        if request["bindingRevision"] != self.binding.revision:
            raise PaperclipError("COMPANY_BINDING_CHANGED", status=409)
        if await self._health() != DONOR_REVISION:
            raise PaperclipError("SOURCE_REVISION_CHANGED", status=409)
        await self._company()
        if request.get("projectId"):
            await self._owned("project", request["projectId"])
        key = self._request_key(request["requestId"])
        description = request["description"] + "\n\n<!-- " + key + " -->"
        # No assignee, wake, resume, interrupt, model or execution-policy input.
        # Existing upstream organization automations remain their owner's concern.
        body = {"title": request["title"], "description": description, "status": "backlog",
                "assigneeAgentId": None, "assigneeUserId": None, "idempotencyKey": key,
                "projectId": request.get("projectId"), "priority": "medium"}
        raw = await self._call("POST", self.company_path + "/issues", body=body)
        try:
            if type(raw) is not dict or raw.get("companyId") != self.binding.company_id or raw.get("title") != request["title"] or raw.get("description") != description:
                raise PaperclipError("SOURCE_RECEIPT_INVALID")
            item = project_record("work", raw, self.binding.company_id)
        except PaperclipError:
            raise PaperclipError("SOURCE_OUTCOME_UNCONFIRMED", effect="EFFECT_UNKNOWN") from None
        return {"schema": COMMAND_SCHEMA, "state": "SAVED", "operation": "create_backlog",
                "requestId": request["requestId"], "companyId": self.binding.company_id,
                "bindingRevision": self.binding.revision, "scopeKey": self.binding.scope(self.principal),
                "item": item, "retryAllowed": False, "executionRequested": False}

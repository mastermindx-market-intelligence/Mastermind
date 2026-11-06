"""Closed F12 projections over an explicitly supplied F10 service.

No Macro, SDK, storage or credentials are imported at module load. The caller
owns the service and current quote-grant resolver; authority never comes from
arguments or from producer output.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import asyncio
import re

from . import CONTRACT
from .contracts import ContractViolation, validate_arguments, validate_output
from .runtime import READ_PORT_CONTRACT

FAILURES = {
    "AUTHENTICATION_REQUIRED": "NOT_ENTITLED", "INSUFFICIENT_SCOPE": "NOT_ENTITLED",
    "REPORT_NOT_ENTITLED": "NOT_ENTITLED", "REPORT_NOT_FOUND": "NOT_FOUND",
    "SOURCE_BODY_UNAVAILABLE": "SOURCE_UNAVAILABLE", "TEXT_LAYER_UNAVAILABLE": "SOURCE_UNAVAILABLE",
    "FULL_TEXT_NOT_MATERIALIZED": "SOURCE_UNAVAILABLE", "RETRIEVAL_UNAVAILABLE": "SOURCE_UNAVAILABLE",
    "INVALID_REQUEST": "INVALID_REQUEST", "INTERNAL_UNAVAILABLE": "SOURCE_UNAVAILABLE",
}
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_SOURCE_PRIORITY = ("CATALOG_UNAVAILABLE", "LATEST_REPORT_INVALID", "FUTURE_REPORT_CLOCK",
                    "PRODUCER_STALE", "NO_REPORTS", "SOURCE_FRESH")
_RIO_PRIORITY = ("INVALID", "STALE", "MISSING", "NOT_REQUESTED", "CURRENT")


def _fail(code="INTERNAL_ERROR"):
    raise ContractViolation(code) from None


@dataclass(frozen=True)
class CanonicalReadContext(Mapping):
    """Synthetic-compatible shape; actual composition supplies F10's own class."""
    principal_id: str
    entitlement: str
    scopes: frozenset
    surface: str

    def __getitem__(self, key):
        return {"entitlement": self.entitlement, "scopes": tuple(sorted(self.scopes)),
                "surface": self.surface, "authenticated": True}[key]

    def __iter__(self):
        return iter(("entitlement", "scopes", "surface", "authenticated"))

    def __len__(self):
        return 4


class ResearchPortAdapter:
    def __init__(self, service, quote_limit, mastermind_commit, *, context_type=CanonicalReadContext,
                 operation_runner=None):
        if (not callable(quote_limit) or not callable(context_type)
                or type(mastermind_commit) is not str
                or re.fullmatch(r"[0-9a-f]{40}", mastermind_commit) is None):
            _fail()
        if operation_runner is not None and not callable(operation_runner):
            _fail()
        self._operation_runner = operation_runner
        self._selection_scopes = None
        if operation_runner is not None:
            from .selected_delivery import SelectionScopes
            self._selection_scopes = SelectionScopes(self._bounded_sync)
        self.service = service
        self.quote_limit = quote_limit
        self.mastermind_commit = mastermind_commit
        self.context_type = context_type
        # Four synchronous producer calls at most per process. No private executor.
        self._slots = asyncio.Semaphore(4)

    def context_builder(self, entitlement):
        digest = getattr(entitlement, "subject_digest", None)
        classes = getattr(entitlement, "content_classes", None)
        if (type(digest) is not str or _DIGEST.fullmatch(digest) is None
                or type(classes) is not frozenset or "catalog_metadata" not in classes
                or not classes <= {"catalog_metadata", "report_text", "evidence_passage", "rio_derived"}):
            _fail("NOT_ENTITLED")
        scopes = {"status", "search"}
        if "report_text" in classes:
            scopes.add("fetch")
        if "evidence_passage" in classes:
            scopes.add("find_evidence")
        return self.context_type(principal_id=digest,
                                 entitlement="pro" if scopes - {"status", "search"} else "preview",
                                 scopes=frozenset(scopes), surface="mcp")

    def _context(self, context, operation):
        if (type(context) is not self.context_type or context.surface != "mcp"
                or context.entitlement not in {"pro", "preview"}
                or type(context.principal_id) is not str or _DIGEST.fullmatch(context.principal_id) is None
                or type(context.scopes) is not frozenset
                or not context.scopes <= {"status", "search", "fetch", "find_evidence"}
                or operation not in context.scopes):
            _fail("NOT_ENTITLED")

    def capture_selection(self):
        if self._selection_scopes is None:
            from contextlib import nullcontext
            return nullcontext(None)
        return self._selection_scopes.capture()

    async def _bounded_sync(self, function, *, before_start=None):
        await self._slots.acquire()
        if before_start is not None:
            try:
                admitted = before_start() is True
            except Exception:
                admitted = False
            if not admitted:
                self._slots.release()
                _fail("NOT_ENTITLED")
        try:
            try:
                pending = asyncio.create_task(asyncio.to_thread(function))
            except BaseException:
                self._slots.release()
                raise
            # Cancellation of a caller does not release its still-running producer slot.
            def settled(done):
                self._slots.release()
                if not done.cancelled():
                    # A canceled caller must not leave a producer exception for loop logging.
                    done.exception()
            pending.add_done_callback(settled)
            result = await asyncio.shield(pending)
        except ContractViolation:
            raise
        except Exception:
            _fail()
        return result

    async def _call(self, operation, context, *, _authorization_operation=None,
                    _before_start=None, **kwargs):
        self._context(context, _authorization_operation or operation)
        capture = self._selection_scopes.active() if self._selection_scopes is not None else None
        def produce():
            def call():
                try:
                    return getattr(self.service, operation)(caller_context=context, **kwargs)
                except Exception:
                    # Preserve the incumbent exception boundary. Only the explicit
                    # selection runner may introduce a private guard refusal.
                    _fail()
            return self._operation_runner(call) if self._operation_runner is not None else call()
        try:
            result = await self._bounded_sync(produce, before_start=_before_start)
        except ContractViolation as exc:
            # A selected runner refusal invalidates the whole response. Ordinary
            # per-report negative envelopes are handled after retain below.
            if capture is not None and exc.code == "SOURCE_UNAVAILABLE":
                capture.invalidate()
            raise
        if capture is not None:
            result = capture.retain(result)
        if not isinstance(result, Mapping) or type(result.get("ok")) is not bool:
            _fail()
        if result["ok"] is False:
            _fail(FAILURES.get(result.get("code"), "INTERNAL_ERROR"))
        return result

    async def resolve_evidence_item(self, *, caller_context, item_id):
        """Bridge the incumbent synchronous item owner through the shared limiter.

        The service seam returns {"ok": True, "item": complete_display_dto} or
        its existing negative read envelope. It owns descriptor replay/current
        source visibility. This adapter cannot create or substitute that owner.
        """
        import json
        from .bounded_item_v1 import ITEM_ID_REGEX, evidence_wire

        self._context(caller_context, "find_evidence")
        if type(item_id) is not str or ITEM_ID_REGEX.fullmatch(item_id) is None:
            _fail("INVALID_REQUEST")
        try:
            cap = self.quote_limit(caller_context.principal_id)
        except Exception:
            _fail("NOT_ENTITLED")
        if type(cap) is not int or not 1 <= cap <= 12000:
            _fail("NOT_ENTITLED")
        if not callable(getattr(self.service, "resolve_evidence_item", None)):
            _fail("SOURCE_UNAVAILABLE")
        def current_grant():
            observed = self.quote_limit(caller_context.principal_id)
            return type(observed) is int and observed == cap

        result = await self._call("resolve_evidence_item", caller_context,
                                  _authorization_operation="find_evidence",
                                  _before_start=current_grant, item_id=item_id)
        try:
            if set(result) != {"ok", "item"}:
                _fail()
            # Snapshot the closed bounded DTO before final grant recheck.
            raw = evidence_wire(result["item"], item_id, 1000)
            value = json.loads(raw)
        except ContractViolation:
            raise
        except Exception:
            _fail()
        try:
            current_cap = self.quote_limit(caller_context.principal_id)
        except Exception:
            _fail("NOT_ENTITLED")
        if type(current_cap) is not int or current_cap != cap or len(value["text"]) > cap:
            _fail("NOT_ENTITLED")
        return value

    @staticmethod
    def _source(result):
        source = result["source"]
        if not isinstance(source, Mapping) or source.get("state") not in _SOURCE_PRIORITY:
            _fail()
        return source

    async def __call__(self, name, arguments, context):
        arguments = validate_arguments(name, arguments)
        try:
            output, quote = await self._project(name, arguments, context)
            validate_output(name, output, quote_limit_chars=quote)
            return output
        except ContractViolation:
            raise
        except Exception:
            _fail()

    async def _project(self, name, args, context):
        if name == "research_find_evidence":
            return await self._evidence(args, context)
        operation = {"research_status": "status", "research_search": "search", "research_fetch": "fetch"}[name]
        kwargs = {}
        if operation == "search":
            kwargs = dict(query=args["query"], filters={target:args[key] for key,target in (("institution","institution"), ("from","date_from"), ("to","date_to")) if key in args},
                          limit=args["limit"], cursor=None)
        elif operation == "fetch":
            kwargs = dict(report_id=args["report_id"], selectors={k:args[k] for k in ("segment_start", "max_segments")})
        result = await self._call(operation, context, **kwargs)
        source = self._source(result)
        output = {"contract": CONTRACT, "source_state": source["state"]}
        if operation == "status":
            output.update(producer={"last_success_at": None, "age_seconds": None,
                                    "stale": source["state"] == "PRODUCER_STALE"},
                          catalog={"report_count": source["report_count"]},
                          coverage={"full_text_ratio": result["full_text_coverage"], "rio_ratio": result["rio_coverage"]},
                          degradation=list(source["known_degradation"]),
                          generation={"server_contract": CONTRACT, "read_port_contract": READ_PORT_CONTRACT,
                                      "mastermind_commit": self.mastermind_commit})
        elif operation == "search":
            if result.get("available") is not True:
                _fail("SOURCE_UNAVAILABLE")
            candidates = []
            if len(result["candidates"]) > args["limit"]:
                _fail()
            for row in result["candidates"]:
                candidate = {k:row[k] for k in ("report_id", "title", "institution", "side", "published_at", "rank")}
                for k in ("side", "published_at"):
                    if candidate[k] == "":
                        candidate[k] = None
                candidates.append(candidate)
            output.update(candidates=candidates, coverage_state=result["coverage_state"])
        else:
            if result.get("available") is not True or not isinstance(result.get("report"), Mapping):
                _fail("SOURCE_UNAVAILABLE")
            report = {k:result["report"][k] for k in ("title", "institution", "side", "published_at")}
            if report["side"] is None or report["side"] == "" or report["published_at"] is None or report["published_at"] == "":
                _fail("SOURCE_UNAVAILABLE")
            report["report_id"] = args["report_id"]
            segments = [{"segment_index":row["segment_index"], "page_start":row["page_start"], "page_end":row["page_end"],
                         "byte_start":row["start_byte"], "byte_end":row["end_byte"], "text":row["text"]}
                        for row in result["segments"]]
            if len(segments) > args["max_segments"]:
                _fail()
            if segments and segments[0]["segment_index"] != args["segment_start"]:
                _fail()
            total = result["segment_count_total"]
            next_index = segments[-1]["segment_index"] + 1 if segments else None
            if next_index is not None and next_index >= total:
                next_index = None
            output.update(report=report, provenance={"source_class":"mastermind_private_institutional", "license_class":"internal_licensed"},
                          text_layer_state=result["text_layer_state"], coverage_state=result["coverage_state"],
                          segment_count_total=total, segments=segments, next_segment_start=next_index, rio_state=result["rio_state"])
        return output, None

    async def _evidence(self, args, context):
        self._context(context, "find_evidence")
        try:
            cap = self.quote_limit(context.principal_id)
        except Exception:
            _fail("NOT_ENTITLED")
        if type(cap) is not int or not 1 <= cap <= 12000:
            _fail("NOT_ENTITLED")
        ids = args.get("report_ids")
        implicit = ids is None
        sources, rios, passages, outcomes = [], [], [], []
        if implicit:
            search = await self._call("search", context, query=args["claim"], filters={}, limit=20, cursor=None)
            sources.append(self._source(search)["state"])
            if search.get("available") is not True:
                _fail("SOURCE_UNAVAILABLE")
            ids = [row["report_id"] for row in search["candidates"]]
        ids = list(dict.fromkeys(ids))
        for report_id in ids:
            try:
                current_cap = self.quote_limit(context.principal_id)
            except Exception:
                _fail("NOT_ENTITLED")
            if type(current_cap) is not int or current_cap != cap:
                _fail("NOT_ENTITLED")
            try:
                result = await self._call("find_evidence", context, report_id=report_id,
                                          query=args["claim"], max_passages=args["limit"])
            except ContractViolation as error:
                if error.code not in {"NOT_FOUND", "SOURCE_UNAVAILABLE"}:
                    raise
                outcomes.append("NOT_FOUND" if error.code == "NOT_FOUND" else "UNAVAILABLE")
                continue
            sources.append(self._source(result)["state"])
            rios.append(result["rio_state"])
            state = result["evidence_state"]
            if state not in {"FOUND", "PARTIAL", "NOT_FOUND", "UNAVAILABLE"}:
                _fail()
            rows = result["passages"]
            if (not isinstance(rows, (list, tuple)) or len(rows) > args["limit"] or (state in {"FOUND", "PARTIAL"}) != bool(rows)):
                _fail()
            outcomes.append(state)
            for row in rows:
                if row["report_id"] != report_id:
                    _fail()
                text = row["text"]
                if not isinstance(text, str):
                    _fail()
                if len(text) > min(1200, cap):
                    _fail("NOT_ENTITLED")
                passages.append({"report_id":report_id, "passage_text":text,
                                 "byte_start":row["start_byte"], "byte_end":row["end_byte"],
                                 "text_sha256":row["passage_text_sha256"],
                                 "canonical_text_sha256":row["extracted_text_sha256"], "segment_index":row["segment_index"]})
        selected = passages[:args["limit"]]
        if selected:
            outcome = "PARTIAL" if implicit or any(o in {"PARTIAL", "UNAVAILABLE"} for o in outcomes) else "FOUND"
        else:
            outcome = "NOT_FOUND" if not implicit and outcomes and all(o == "NOT_FOUND" for o in outcomes) else "UNAVAILABLE"
        source = next((s for s in _SOURCE_PRIORITY if s in sources), "CATALOG_UNAVAILABLE")
        rio = next((r for r in _RIO_PRIORITY if r in rios), "NOT_REQUESTED")
        return {"contract":CONTRACT, "source_state":source, "outcome":outcome,
                "passages":selected, "rio_state":rio}, cap


def compose_macro_service(release, commit, tree, *, release_verifier):
    return _compose_macro_service(release, commit, tree, release_verifier=release_verifier)


def compose_selected_macro_service(release, commit, tree, *, release_verifier, options, clock):
    from .selected_factory import SelectedReadOptions
    if type(options) is not SelectedReadOptions or not callable(clock):
        _fail("SOURCE_UNAVAILABLE")
    options.validate()
    return _compose_macro_service(release, commit, tree, release_verifier=release_verifier,
                                  selected_options=options, selected_clock=clock)


def _compose_macro_service(release, commit, tree, *, release_verifier,
                           selected_options=None, selected_clock=None):
    """Explicit single-process import of the qualified immutable Macro release.

    The source owner verifies exact bytes before any import. A foreign existing
    namespace refuses instead of silently borrowing another checkout's code.
    This factory supplies no credentials, local-store fallback or readiness.
    """
    import importlib
    import os
    from pathlib import Path
    import sys

    if (type(release) is not str or any(type(value) is not str
            or re.fullmatch(r"[0-9a-f]{40}", value) is None for value in (commit,tree))):
        _fail()
    root = Path(release)
    owned = ("engine", "lib", "scripts")
    if (not root.is_absolute() or str(root) != release or root.name != commit
            or any(p.is_symlink() for p in (root, *root.parents))
            or (root / ".git").exists() or (root / ".env").exists()
            or os.environ.get("RESEARCH_LOCAL_STORE")
            or any(name.split(".")[0] in owned for name in sys.modules)
            or not callable(release_verifier)):
        _fail()
    try:
        if release_verifier(release, commit, tree) is not None:
            _fail()
    except Exception:
        _fail()
    initial_modules = set(sys.modules)
    initial_path = list(sys.path)
    try:
        sys.path.insert(0, release)
        runtime = importlib.import_module("engine.research_vault.read_runtime")
        port = importlib.import_module("engine.research_vault.read_port")
        service_module = importlib.import_module("engine.research_vault.read_service")
        if port.READ_SCHEMA != READ_PORT_CONTRACT or set(port.FAILURE_CODES) != set(FAILURES):
            _fail()
        # Qualify all owned module files before invoking the actual factory.
        def provenance():
            for name, module in tuple(sys.modules.items()):
                if name.split(".")[0] not in owned:
                    continue
                path = getattr(module, "__file__", None)
                if path is None or not Path(path).resolve().is_relative_to(root.resolve()):
                    _fail()
            if any(name.split(".")[0] == "app" for name in set(sys.modules) - initial_modules):
                _fail()
        selected = None
        if selected_options is not None:
            reader = importlib.import_module("engine.research_vault.qualified_reader")
            store = importlib.import_module("engine.research_vault.r2_store")
            provenance()
            from .selected_factory import build_selected
            selected = build_selected(runtime, service_module, reader, store,
                                      selected_options, selected_clock)
            service = selected.service
        else:
            provenance()
            service = runtime.build_read_service()
        provenance()
        if type(service) is not service_module.ResearchReadService:
            _fail()
        receipt = {
            "state":"PINNED_MACRO_FACTORY_COMPOSED", "commit":commit, "tree":tree,
            "factory_module":"engine.research_vault.read_runtime", "factory_file":str(Path(runtime.__file__).resolve()),
            "read_port_contract":port.READ_SCHEMA, "production_readiness":False,
        }
        if selected is not None:
            selected.receipt = dict(receipt, state="PINNED_SELECTED_MACRO_FACTORY_COMPOSED",
                                    expected_producer_commit=selected_options.expected_producer_commit)
            # Complete preparation before any listener or request is constructed.
            selected.prepare()
            provenance()
            return selected
        return service, service_module.ServerReadContext, receipt
    except Exception as exc:
        for name in set(sys.modules) - initial_modules:
            if name.split(".")[0] in owned:
                sys.modules.pop(name, None)
        if isinstance(exc, ContractViolation):
            raise
        _fail()
    finally:
        sys.path[:] = initial_path

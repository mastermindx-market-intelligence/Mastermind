"""Request-local immutable result of the issued canonical CREATE compiler.

This is compilation evidence, never a write grant or publication receipt. It
keeps repeated pure recipe checks inside one request from re-running the sealed
child; a different request or programme set cannot use the captured result.
"""
from __future__ import annotations
import hashlib
import json

_ISSUER = object()


def _bytes(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


class CapturedProjectCreationCompilation:
    OUTPUT_SCHEMA = "agentos.project_proposal.v1"
    DRAFT_STATE = "DRAFT_ONLY"
    WORKSTREAM_DIR = "agentos/workstreams"
    __slots__ = ("_request", "_recipe", "_binding", "_programs", "_current", "_issuer")

    def __init__(self, request, capture, *, current, issuer):
        if issuer is not _ISSUER or not callable(current) or current() is not True:
            raise ValueError("PROJECT_CREATION_COMPILATION_UNAVAILABLE")
        self._request, self._recipe = _bytes(request), _bytes(capture["recipe"])
        self._binding, self._programs = _bytes(capture["source_binding"]), frozenset(capture["programs"])
        self._current, self._issuer = current, issuer

    @property
    def source_binding(self):
        return json.loads(self._binding)

    @property
    def programs(self):
        return self._programs

    def compile_proposal(self, request, *, programs):
        if (self._issuer is not _ISSUER or self._current() is not True
                or type(request) is not dict or type(programs) not in (set, frozenset)
                or programs != self._programs or _bytes(request) != self._request):
            raise ValueError("PROJECT_CREATION_COMPILATION_UNAVAILABLE")
        value = json.loads(self._recipe)
        if (value.get("request_sha256") != hashlib.sha256(self._request).hexdigest()
                or value.get("content_sha256") != hashlib.sha256(value["content_utf8"].encode("utf-8")).hexdigest()):
            raise ValueError("PROJECT_CREATION_COMPILATION_UNAVAILABLE")
        return value


def _issue_creation_compilation(request, capture, *, current):
    return CapturedProjectCreationCompilation(request, capture, current=current, issuer=_ISSUER)

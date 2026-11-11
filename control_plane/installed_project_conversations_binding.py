"""Nominal installed conversation READ binding, with no integration imports.

Private issuers retain the actual reader/method/source identities. This is
constructor evidence, never an authentication grant or public frame selector.
"""
from dataclasses import dataclass
from types import FunctionType, MethodType

_KEY = object()


def _fail():
    raise ValueError("project conversation reader unavailable")


def _methods(owner):
    result = []
    for name in ("catalogue", "read", "execution_references", "execution_read"):
        method = getattr(owner, name)
        if (type(method) is not MethodType or method.__self__ is not owner
                or type(owner).__dict__.get(name) is not method.__func__):
            _fail()
        result.append((method, method.__func__.__code__))
    return tuple(result)


@dataclass(frozen=True, slots=True)
class _ProjectConversationsBinding:
    key: object
    owner: object
    runtime: object
    store: object
    source: tuple
    execution_source: tuple | None
    methods: tuple
    qualifier: object
    qualifier_code: object

    def check(self, runtime):
        if (type(self) is not _ProjectConversationsBinding or self.key is not _KEY
                or runtime is not self.runtime or runtime.store is not self.store
                or type(self.qualifier) is not FunctionType
                or self.qualifier.__code__ is not self.qualifier_code
                or self.qualifier(self.owner) is not True
                or self.owner._runtime is not runtime or self.owner._source != self.source
                or self.owner._execution_source != self.execution_source
                or _methods(self.owner) != self.methods):
            _fail()
        return self

    def catalogue(self, principal, arguments, *, guard):
        self.check(self.runtime)
        result = self.methods[0][0](principal, arguments, guard=guard)
        self.check(self.runtime)
        return result

    async def read(self, principal, arguments, *, guard):
        self.check(self.runtime)
        result = await self.methods[1][0](principal, arguments, guard=guard)
        self.check(self.runtime)
        return result

    def execution_references(self, principal, arguments, *, guard):
        self.check(self.runtime)
        result = self.methods[2][0](principal, arguments, guard=guard)
        self.check(self.runtime)
        return result

    async def execution_read(self, principal, arguments, *, guard):
        self.check(self.runtime)
        result = await self.methods[3][0](principal, arguments, guard=guard)
        self.check(self.runtime)
        return result


def _issue_project_conversations(owner, *, qualifier):
    if type(qualifier) is not FunctionType or qualifier(owner) is not True:
        _fail()
    methods = _methods(owner)
    binding = _ProjectConversationsBinding(_KEY, owner, owner._runtime,
        owner._runtime.store, owner._source, owner._execution_source, methods, qualifier, qualifier.__code__)
    return binding.check(owner._runtime)


def require_installed_project_conversations(binding, runtime):
    if type(binding) is not _ProjectConversationsBinding:
        _fail()
    return binding.check(runtime)

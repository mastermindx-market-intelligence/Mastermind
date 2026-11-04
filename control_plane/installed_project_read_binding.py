"""Opaque, process-local composition for the installed Agent OS readers.

The integration owns collector qualification and issuance. Core reads no
integration module, accepts no serialized grant and creates no reader registry.
The callback remains inside its incumbent collector source-seal bracket.
"""
from dataclasses import dataclass
from pathlib import Path
from types import MethodType
from typing import Callable
import weakref

_ISSUE_KEY = object()
_METHODS = {"project_plan": "read_project_plan", "project_journal": "read_project_journal",
            "project_creation_source": "read_project_creation_source",
            "project_direction": "read_project_direction", "project_archive": "read_project_archive"}
_COORDINATES = ("_source_root", "_macro_root", "_code_root", "_python",
                "_expected_source_sha", "_allow_synthetic_fixture")


class InstalledProjectReadUnavailable(ValueError):
    pass


def _context(owner):
    return tuple(getattr(owner, field) for field in _COORDINATES)


@dataclass(frozen=True, slots=True)
class _InstalledReadBinding:
    seal: object
    reader: weakref.ReferenceType
    owner: object
    kind: str
    macro_root: Path
    context: tuple
    callback: MethodType
    qualified_owner: Callable[[object], bool]

    def __post_init__(self):
        if self.seal is not _ISSUE_KEY:
            raise InstalledProjectReadUnavailable("SOURCE_UNAVAILABLE")


def _issue_installed_project_read(reader, *, owner, kind, qualified_owner):
    """Private composition API, called after the installed factory's checks.

    Qualification is an integration-owned nominal check, not a caller label or
    a duck-typed read method. Public facade constructors never issue a binding.
    """
    if kind not in _METHODS or not qualified_owner(owner):
        raise InstalledProjectReadUnavailable("SOURCE_UNAVAILABLE")
    callback = getattr(owner, _METHODS[kind])
    if (type(callback) is not MethodType or callback.__self__ is not owner
            or type(owner).__dict__.get(_METHODS[kind]) is not callback.__func__):
        raise InstalledProjectReadUnavailable("SOURCE_UNAVAILABLE")
    return _InstalledReadBinding(_ISSUE_KEY, weakref.ref(reader), owner, kind,
        reader._macro_root.resolve(), _context(owner), callback, qualified_owner)


def _matches(binding, *, reader, owner, kind):
    if (type(binding) is not _InstalledReadBinding or binding.seal is not _ISSUE_KEY
            or binding.reader() is not reader or binding.owner is not owner
            or binding.kind != kind):
        return False
    try:
        if not binding.qualified_owner(owner):
            return False
        live = getattr(owner, _METHODS[kind])
        return (_context(owner) == binding.context
                and reader._installed_context_binding == binding.context
                and reader._macro_root.resolve() == binding.macro_root == owner._macro_root
                and type(live) is MethodType and live.__self__ is owner
                and live.__func__ is binding.callback.__func__
                and type(owner).__dict__.get(_METHODS[kind]) is binding.callback.__func__)
    except (AttributeError, TypeError, ValueError):
        return False


def read_installed_project_binding(reader, *, kind, work_ref):
    binding = reader._installed_reader_binding
    owner = reader._installed_context_owner
    if not _matches(binding, reader=reader, owner=owner, kind=kind):
        raise InstalledProjectReadUnavailable("SOURCE_UNAVAILABLE")
    value = binding.callback(work_ref=work_ref)
    if not _matches(binding, reader=reader, owner=owner, kind=kind):
        raise InstalledProjectReadUnavailable("SOURCE_UNAVAILABLE")
    return value


def read_installed_project_archive_binding(reader, *, work_refs, expected_current_macro_sha):
    """Only the server-qualified bounded catalogue may select archive members."""
    from common import workspace_project_archive_contract as wire
    refs = wire.validate_refs(work_refs)
    if not wire._hex(expected_current_macro_sha, 40):
        raise InstalledProjectReadUnavailable("SOURCE_UNAVAILABLE")
    binding, owner = reader._installed_reader_binding, reader._installed_context_owner
    if not _matches(binding, reader=reader, owner=owner, kind="project_archive"):
        raise InstalledProjectReadUnavailable("SOURCE_UNAVAILABLE")
    value = binding.callback(work_refs=refs, expected_current_macro_sha=expected_current_macro_sha)
    if not _matches(binding, reader=reader, owner=owner, kind="project_archive"):
        raise InstalledProjectReadUnavailable("SOURCE_UNAVAILABLE")
    return value


def read_installed_project_creation_binding(reader, *, work_ref, record_commit, expected_current_macro_sha=None):
    """Fixed historical creation read; no arbitrary kwargs or current-root guess."""
    import re
    if type(record_commit) is not str or re.fullmatch(r"[0-9a-f]{40}", record_commit) is None:
        raise InstalledProjectReadUnavailable("SOURCE_UNAVAILABLE")
    binding = reader._installed_reader_binding
    owner = reader._installed_context_owner
    if not _matches(binding, reader=reader, owner=owner, kind="project_creation_source"):
        raise InstalledProjectReadUnavailable("SOURCE_UNAVAILABLE")
    if expected_current_macro_sha is not None and (type(expected_current_macro_sha) is not str or re.fullmatch(r"[0-9a-f]{40}", expected_current_macro_sha) is None):
        raise InstalledProjectReadUnavailable("SOURCE_UNAVAILABLE")
    kwargs = {"work_ref": work_ref, "record_commit": record_commit}
    if expected_current_macro_sha is not None:
        kwargs["expected_current_macro_sha"] = expected_current_macro_sha
    value = binding.callback(**kwargs)
    if not _matches(binding, reader=reader, owner=owner, kind="project_creation_source"):
        raise InstalledProjectReadUnavailable("SOURCE_UNAVAILABLE")
    return value

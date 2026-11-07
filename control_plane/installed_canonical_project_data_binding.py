"""Opaque installed latest-DATA READ binding; no integration import/store."""
from dataclasses import dataclass
from types import MethodType
import re

_KEY=object()
@dataclass(frozen=True,slots=True)
class _ProjectDataReadBinding:
    key:object
    owner:object
    store:object
    callback:MethodType
    context:tuple
    context_callback:MethodType
    qualifier:object


def _issue_project_data_read(owner,*,qualifier):
    callback=owner.read_knowledge
    if (qualifier(owner) is not True or type(callback) is not MethodType
            or callback.__self__ is not owner or type(owner).__dict__.get('read_knowledge') is not callback.__func__):
        raise ValueError('CANONICAL_DATA_UNAVAILABLE')
    context_callback=owner.context_binding
    if (type(context_callback) is not MethodType or context_callback.__self__ is not owner
            or type(owner).__dict__.get('context_binding') is not context_callback.__func__):
        raise ValueError('CANONICAL_DATA_UNAVAILABLE')
    return _ProjectDataReadBinding(_KEY,owner,owner.events.store,callback,context_callback(),context_callback,qualifier)


def read_installed_project_data(binding,principal,*,operation,selection):
    def current():
        return (type(binding) is _ProjectDataReadBinding and binding.key is _KEY
            and binding.qualifier(binding.owner) is True
            and binding.owner.context_binding==binding.context_callback
            and type(binding.owner).__dict__.get('context_binding') is binding.context_callback.__func__
            and binding.context_callback()==binding.context
            and binding.owner.read_knowledge==binding.callback
            and type(binding.owner).__dict__.get('read_knowledge') is binding.callback.__func__)
    if not current():raise ValueError('CANONICAL_DATA_UNAVAILABLE')
    result=binding.callback(principal,operation=operation,selection=selection)
    if not current():raise ValueError('CANONICAL_DATA_UNAVAILABLE')
    if result is None:return None
    from control_plane.project_canonical_data import CanonicalProjectDataView
    if (type(result) is not tuple or len(result)!=3 or type(result[0]) is not dict
            or type(result[1]) is not CanonicalProjectDataView or type(result[2]) is not str
            or re.fullmatch(r'[0-9a-f]{64}',result[2]) is None):raise ValueError('CANONICAL_DATA_UNAVAILABLE')
    result[1].check()
    return result

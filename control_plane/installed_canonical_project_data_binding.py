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
    plan_callback:MethodType
    agentos_context_callback:MethodType


def _issue_project_data_read(owner,*,qualifier):
    callback=owner.read_knowledge
    if (qualifier(owner) is not True or type(callback) is not MethodType
            or callback.__self__ is not owner or type(owner).__dict__.get('read_knowledge') is not callback.__func__):
        raise ValueError('CANONICAL_DATA_UNAVAILABLE')
    context_callback=owner.context_binding
    if (type(context_callback) is not MethodType or context_callback.__self__ is not owner
            or type(owner).__dict__.get('context_binding') is not context_callback.__func__):
        raise ValueError('CANONICAL_DATA_UNAVAILABLE')
    plan_callback=owner.read_plan
    if (type(plan_callback) is not MethodType or plan_callback.__self__ is not owner
            or type(owner).__dict__.get('read_plan') is not plan_callback.__func__):
        raise ValueError('CANONICAL_DATA_UNAVAILABLE')
    agentos_context_callback=owner.read_context
    if (type(agentos_context_callback) is not MethodType or agentos_context_callback.__self__ is not owner
            or type(owner).__dict__.get('read_context') is not agentos_context_callback.__func__):
        raise ValueError('CANONICAL_DATA_UNAVAILABLE')
    return _ProjectDataReadBinding(_KEY,owner,owner.events.store,callback,context_callback(),context_callback,
                                  qualifier,plan_callback,agentos_context_callback)


def read_installed_project_data(binding,principal,*,operation,selection):
    def current():
        return (type(binding) is _ProjectDataReadBinding and binding.key is _KEY
            and binding.qualifier(binding.owner) is True
            and binding.owner.context_binding==binding.context_callback
            and type(binding.owner).__dict__.get('context_binding') is binding.context_callback.__func__
            and binding.context_callback()==binding.context
            and binding.owner.read_knowledge==binding.callback
            and type(binding.owner).__dict__.get('read_knowledge') is binding.callback.__func__
            and binding.owner.read_plan==binding.plan_callback
            and type(binding.owner).__dict__.get('read_plan') is binding.plan_callback.__func__
            and binding.owner.read_context==binding.agentos_context_callback
            and type(binding.owner).__dict__.get('read_context') is binding.agentos_context_callback.__func__)
    if not current():raise ValueError('CANONICAL_DATA_UNAVAILABLE')
    if operation not in {'project_plan','project_knowledge_catalogue','project_knowledge_memory',
                          'project_knowledge_source','project_discovery_source','agentos_current_context'}:
        raise ValueError('CANONICAL_DATA_UNAVAILABLE')
    callback=(binding.plan_callback if operation=='project_plan' else binding.agentos_context_callback
              if operation=='agentos_current_context' else binding.callback)
    result=callback(principal,operation=operation,selection=selection)
    if not current():raise ValueError('CANONICAL_DATA_UNAVAILABLE')
    if result is None:return None
    from control_plane.project_canonical_data import CanonicalProjectDataView
    if (type(result) is not tuple or len(result)!=3 or type(result[0]) is not dict
            or type(result[1]) is not CanonicalProjectDataView or type(result[2]) is not str
            or re.fullmatch(r'[0-9a-f]{64}',result[2]) is None):raise ValueError('CANONICAL_DATA_UNAVAILABLE')
    result[1].check()
    return result

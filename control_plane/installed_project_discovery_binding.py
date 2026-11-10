"""Opaque fixed installed discovery binding. No integration import or store."""
from dataclasses import dataclass
from types import MethodType

_KEY = object()


@dataclass(frozen=True, slots=True)
class _ProjectDiscoveryBinding:
    key: object
    owner: object
    store: object
    callback: object
    context: tuple
    context_callback: object
    qualifier: object


def _issue_project_discovery(owner, *, qualifier):
    callback, current = owner.capture, owner.context_binding
    if (qualifier(owner) is not True or type(callback) is not MethodType
            or callback.__self__ is not owner or type(owner).__dict__.get('capture') is not callback.__func__
            or type(current) is not MethodType or current.__self__ is not owner
            or type(owner).__dict__.get('context_binding') is not current.__func__):
        raise ValueError('PROJECT_DISCOVERY_UNAVAILABLE')
    return _ProjectDiscoveryBinding(_KEY, owner, owner.data.events.store, callback, current(), current, qualifier)


def read_installed_project_discovery(binding, frame, *, runtime, work_ref=None,
        include_plan=False, deadline=None, plan_binding=None):
    if type(include_plan) is not bool or include_plan and work_ref is None:
        raise ValueError('PROJECT_DISCOVERY_UNAVAILABLE')
    from control_plane.workspace_owned_task import remaining_read_seconds
    def check():
        remaining_read_seconds(deadline, maximum=15.0)
        if (type(binding) is not _ProjectDiscoveryBinding or binding.key is not _KEY
                or binding.qualifier(binding.owner) is not True or runtime.store is not binding.store
                or binding.owner.capture != binding.callback or binding.owner.context_binding != binding.context_callback
                or type(binding.owner).__dict__.get('capture') is not binding.callback.__func__
                or type(binding.owner).__dict__.get('context_binding') is not binding.context_callback.__func__
                or binding.context_callback() != binding.context):
            raise ValueError('PROJECT_DISCOVERY_UNAVAILABLE')
        if include_plan:
            from control_plane.installed_canonical_project_data_binding import require_installed_project_data_owner
            require_installed_project_data_owner(plan_binding, owner=binding.owner.data, store=runtime.store)
    check()
    options = {}
    if include_plan:
        options['include_plan'] = True
    if deadline is not None:
        options['deadline'] = deadline
    result = binding.callback(frame, work_ref=work_ref, **options)
    try:
        check()
        if result is None:
            return None
        result.check()
        return result
    except Exception:
        if result is not None:
            result.close()
        raise

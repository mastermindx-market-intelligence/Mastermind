"""Closed direct-native origin syntax beside its actual Runtime owner proof."""
from control_plane import runtime_root_origin as legacy


def validate_direct_origin(job, event, material):
    # Shared immutable root/Event identity grammar remains owned by Runtime.
    job_id = legacy._validate_job(job)
    payload = legacy._validate_event(job, event, job_id)
    legacy._reject_orchestration_metadata(payload)
    provenance = payload.get('provenance')
    keys = set(legacy._PROVENANCE_KEYS) | {'direct_native'}
    if 'project_planning' in material:
        keys.add('project_planning_sha256')
    if (type(provenance) is not dict or set(provenance) != keys
            or provenance['schema'] != 'mastermind.ceo_direct_native_intent.v1'
            or type(provenance['intent_id']) is not str or legacy._INTENT_ID_RE.fullmatch(provenance['intent_id']) is None
            or type(provenance['actor']) is not str or legacy._ACTOR_RE.fullmatch(provenance['actor']) is None
            or type(provenance['fingerprint']) is not str or legacy._LOWER_HEX64_RE.fullmatch(provenance['fingerprint']) is None
            or legacy._command_id(event) != 'ceo-intent:' + provenance['intent_id']
            or provenance['direct_native'] != material
            or provenance['workstream'] != material['source']['work_ref']):
        raise ValueError('DIRECT_ROOT_ORIGIN_UNAVAILABLE')
    grounding = provenance['grounding']
    from control_plane.ceo_intent import _grounding
    # Direct-native intents use the actual CEO owner's two required SHA
    # fields and optional original packet label, not legacy v1's closed three.
    if (_grounding(grounding) != grounding
            or grounding['mastermind_sha'] != material['binding']['base_sha']):
        raise ValueError('DIRECT_ROOT_ORIGIN_UNAVAILABLE')
    if 'project_planning' in material:
        planning = material['project_planning']
        from control_plane.direct_native_execution import digest
        if (grounding['macro_sha'] != planning['source']['commit']
                or provenance['project_planning_sha256'] != digest(planning)):
            raise ValueError('DIRECT_ROOT_ORIGIN_UNAVAILABLE')
    return dict(provenance)

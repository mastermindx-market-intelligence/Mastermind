"""Fixed Programs/Mission extension over an issued request-local DATA reader."""
from copy import deepcopy

from common.executive_workspace_contract import digest, bounded_canonical, MAX_RESPONSE_BYTES
from common.project_discovery_observation_contract import validate_observation
from control_plane.installed_project_discovery_binding import read_installed_project_discovery
from control_plane.project_discovery_projection import runtime_metadata, compose_data_project


def _stable(service, before):
    from control_plane.workspace_read_service import _qualified, _observation
    after = service.cache.snapshot()
    if not _qualified(after):
        raise ValueError('source_unavailable')
    observation = _observation(before, after, None, None)
    if observation['state'] != 'SAME':
        raise ValueError('source_unavailable')
    return observation


def _capture(service, frame, before, *, work_ref=None):
    capture = read_installed_project_discovery(service._project_discovery, frame['principal'],
        runtime=service.runtime, work_ref=work_ref)
    if capture is None:
        if work_ref is not None:
            raise ValueError('source_unavailable')
        return None, None
    try:
        material = capture.document()
        code = before.document.get('sources', {}).get('macro_sha')
        if any(entry['data_observation']['executable_macro_commit'] != code for entry in material['entries']):
            raise ValueError('source_unavailable')
        return capture, material
    except Exception:
        capture.close()
        raise


def read_programs(service, frame, before):
    capture, material = _capture(service, frame, before)
    if capture is None:
        return None
    try:
        # Existing C rows retain their exact doc, time, digest and validity.
        # A current N record replaces no published C row in this finite slice.
        present = {row['work_ref'] for row in before.document['work']}
        entries = [item for item in material['entries'] if item['record']['selection']['work_ref'] not in present]
        if not entries and material['coverage']['state'] == 'COMPLETE':
            return None
        works = {entry['record']['selection']['work_ref'] for entry in entries}
        runtime = service._bounded_runtime(service.runtime) if service._bounded_runtime else service.runtime
        roots, receipt = (runtime_metadata(runtime, works, creation_publications={entry['record']['selection']['work_ref']: entry['creation_publication'] for entry in entries})
            if entries else (dict(rows=[], origins=[]), None))
        observation = _stable(service, before)
        projects = [compose_data_project(item, runtime_rows=roots['rows'], runtime_receipt=receipt,
            configured_observation=observation) for item in entries]
        roots_after, receipt_after = (runtime_metadata(runtime, works, creation_publications={entry['record']['selection']['work_ref']: entry['creation_publication'] for entry in entries})
            if entries else (roots, None))
        if roots_after != roots:
            raise ValueError('source_unavailable')
        capture.check()
        observation = _stable(service, before)
        for project in projects:
            project['source_observation']['control_room'] = deepcopy(observation['control_room'])
            validate_observation(project['source_observation'], work_ref=project['work_ref'], root_job_id=None,
                document=project['control_room'], validity=project['source_validity'], currentness=project['cache_currentness'])
        result = dict(schema='mastermind.workspace_programs.v2', availability='AVAILABLE',
            control_room=before.document, source_observation=observation, reason_codes=[],
            canonical_projects=projects, coverage=dict(material['coverage'], returned=len(projects)))
        response = dict(ok=True, result=result)
        bounded_canonical(response, limit=MAX_RESPONSE_BYTES - 1)
        return response
    finally:
        capture.close()


def read_mission(service, frame, before):
    from control_plane.workspace_read_service import _join
    from control_plane.fabric_job_view import read_fabric_view_v3_from_runtime
    from control_plane.mission_workspace import compose_mission_workspace_v3
    selected = frame['selection']
    capture, material = _capture(service, frame, before, work_ref=selected['work_ref'])
    try:
        if len(material['entries']) != 1:
            raise LookupError('selection_not_found')
        runtime = service._bounded_runtime(service.runtime) if service._bounded_runtime else service.runtime
        roots, receipt = runtime_metadata(runtime, {selected['work_ref']}, creation_publications={selected['work_ref']: material['entries'][0]['creation_publication']})
        observation = _stable(service, before)
        project = compose_data_project(material['entries'][0], runtime_rows=roots['rows'], runtime_receipt=receipt,
            configured_observation=observation)
        _join(project['control_room'], selected)
        acquire = service._mission_v3_acquire or read_fabric_view_v3_from_runtime
        companion = acquire(runtime, selected['root_job_id'], armed=service.armed, runtime_identity=service.runtime_identity)
        acquisition = companion.get('fabric_view', {}).get('runtime', {}).get('acquisition', {})
        generation = acquisition.get('generation')
        if type(generation) is not dict or generation.get('state') != 'SAME':
            raise ValueError('source_unavailable')
        roots_after, after_receipt = runtime_metadata(runtime, {selected['work_ref']}, creation_publications={selected['work_ref']: material['entries'][0]['creation_publication']})
        if roots_after != roots:
            raise ValueError('source_unavailable')
        capture.check()
        base_observation = _stable(service, before)
        # Refresh only elapsed-budget samples on this same N card; the source
        # generation, canonical record time and old C cache remain unchanged.
        project = compose_data_project(material['entries'][0], runtime_rows=roots['rows'], runtime_receipt=receipt,
            configured_observation=base_observation)
        owner = project['source_observation']
        owner['selection'] = deepcopy(selected)
        owner['runtime'] = dict(generation, snapshot_digest=acquisition.get('snapshot_digest'))
        validate_observation(owner, **selected, document=project['control_room'],
            validity=project['source_validity'], currentness=project['cache_currentness'], fabric=companion['fabric_view'])
        compose = service._mission_v3_compose or compose_mission_workspace_v3
        result = compose(control_room=project['control_room'], fabric_view=companion, **selected,
            source_validity=project['source_validity'], cache_currentness=project['cache_currentness'],
            source_generation=None, owner_observation=owner)
        response = dict(ok=True, result=result)
        bounded_canonical(response, limit=MAX_RESPONSE_BYTES - 1)
        return response
    finally:
        capture.close()

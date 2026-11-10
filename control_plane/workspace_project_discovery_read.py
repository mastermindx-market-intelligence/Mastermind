"""Fixed Programs/Mission extension over an issued request-local DATA reader."""
from copy import deepcopy

from common.executive_workspace_contract import digest, bounded_canonical, MAX_RESPONSE_BYTES
from common.project_discovery_observation_contract import validate_observation
from control_plane.installed_project_discovery_binding import read_installed_project_discovery
from control_plane.project_discovery_projection import runtime_metadata, compose_data_project, root_history


def _stable(service, before):
    from control_plane.workspace_read_service import _qualified, _observation
    after = service.cache.snapshot()
    if not _qualified(after):
        raise ValueError('source_unavailable')
    observation = _observation(before, after, None, None)
    if observation['state'] != 'SAME':
        raise ValueError('source_unavailable')
    return observation


def _capture(service, frame, before, *, work_ref=None, include_plan=False, deadline=None):
    capture = read_installed_project_discovery(service._project_discovery, frame['principal'],
        runtime=service.runtime, work_ref=work_ref, include_plan=include_plan, deadline=deadline,
        plan_binding=service._canonical_project_data if include_plan else None)
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
        with_execution_history = any(row['execution'] is not None
            for items in roots.get('history', {}).values() for row in items)
        capture.check()
        observation = _stable(service, before)
        for project in projects:
            project['source_observation']['control_room'] = deepcopy(observation['control_room'])
            validate_observation(project['source_observation'], work_ref=project['work_ref'], root_job_id=None,
                document=project['control_room'], validity=project['source_validity'], currentness=project['cache_currentness'])
            if with_execution_history:
                project['root_history'] = root_history(roots_after, receipt_after, work_ref=project['work_ref'])
        result = dict(schema='mastermind.workspace_programs.v3' if with_execution_history else
            'mastermind.workspace_programs.v2', availability='AVAILABLE',
            control_room=before.document, source_observation=observation, reason_codes=[],
            canonical_projects=projects, coverage=dict(material['coverage'], returned=len(projects)))
        response = dict(ok=True, result=result)
        bounded_canonical(response, limit=MAX_RESPONSE_BYTES - 1)
        return response
    finally:
        capture.close()


def read_mission(service, frame, before, *, project_help=False, deadline=None):
    from control_plane.workspace_read_service import _join, _retained_root_join
    from common.project_execution_resource_contract import resource_from_history
    from control_plane.fabric_job_view import read_fabric_view_v3_from_runtime
    from control_plane.mission_workspace import compose_mission_workspace_v3
    selected = frame['selection']
    capture, material = _capture(service, frame, before, work_ref=selected['work_ref'],
        include_plan=project_help, deadline=deadline)
    try:
        if len(material['entries']) != 1:
            raise LookupError('selection_not_found')
        runtime = service._bounded_runtime(service.runtime) if service._bounded_runtime else service.runtime
        roots, receipt = runtime_metadata(runtime, {selected['work_ref']}, creation_publications={selected['work_ref']: material['entries'][0]['creation_publication']})
        observation = _stable(service, before)
        project = compose_data_project(material['entries'][0], runtime_rows=roots['rows'], runtime_receipt=receipt,
            configured_observation=observation)
        history = root_history(roots, receipt, work_ref=selected['work_ref'])
        selected_origins = [row for row in history['roots'] if row['root_job_id'] == selected['root_job_id']]
        resource = None
        if len(selected_origins) == 1 and selected_origins[0]['execution'] is not None:
            # Project-wide history stays intact in Programs. This separate
            # resource read is selected only through the original immutable
            # ProjectExecution admission and exact published root membership.
            # It grants no Mission selection or fresh execution authority.
            _retained_root_join(project['control_room'], selected)
            resource = resource_from_history(history, root_job_id=selected['root_job_id'])
            project = compose_data_project(material['entries'][0], runtime_rows=roots['rows'],
                runtime_receipt=receipt, configured_observation=observation, execution_resource=resource)
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
            configured_observation=base_observation, execution_resource=resource)
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
        if project_help:
            response['help_read_qualification'] = _project_help_qualification(project, result, selected,
                roots=roots_after, creation=material['entries'][0]['creation_publication'],
                **({'execution_resource': True} if resource is not None else {}))
            response['help_plan'] = deepcopy(material['entries'][0]['plan'])
        bounded_canonical(response, limit=MAX_RESPONSE_BYTES - 1)
        return response
    finally:
        capture.close()


def _project_help_qualification(project, mission, selected, *, roots, creation, execution_resource=False):
    """Current DATA/card/root evidence for this read, with transport unproved.

    Called only inside the existing acquisition, before its issued capture is
    closed. The ordinary Mission remains PARTIAL, and neither the generic
    mandate nor any effect gate accepts this as a current execution mission.
    """
    from control_plane import mission_workspace as mw
    from control_plane.coo_principal_mandate import _mission_state
    if execution_resource:
        from common.project_execution_resource_contract import validate_resource
        resource = validate_resource(project['source_observation'].get('resource'), **selected)
        body = mission['mission']
        if (mission.get('schema') != 'mastermind.mission_workspace.v3'
                or mission['program']['work_ref'] != selected['work_ref']
                or body['root_job_id'] != selected['root_job_id']
                or body['root_job_candidates'] != [selected['root_job_id']]
                or body['root_job_ambiguous'] is not False or body['runtime_root_state'] != 'RESOLVED'
                or resource['history']['roots'] != roots['history'][selected['work_ref']]):
            raise ValueError('source_unavailable')
    else:
        state = _mission_state(mission, expected_work_ref=selected['work_ref'])
        if state.qualified:
            return None
        if state.reason_codes != ('mission_read_state_not_current',) or state.root_job_id != selected['root_job_id']:
            raise ValueError('source_unavailable')
    transport = mission['transport']
    expected_transport = dict(dispatch_state='UNKNOWN', reason='dispatch_evidence_not_supplied',
        actionable=False, historical=True, watch_proven=False, carrier=None, w3c=None, evidence=[])
    if (mission['read_state']['state'] != 'PARTIAL'
            or mission['read_state']['reason_codes'] != ['SOURCE_OR_VALIDITY_INCOMPLETE']
            or mission['source']['owner_observation'] != project['source_observation']
            or project['source_observation']['schema'] != ('mastermind.workspace_source_observation.v3'
                if execution_resource else 'mastermind.workspace_source_observation.v2')
            or transport != expected_transport
            or any(row.get('missingness_class') == 'DEGRADED' for row in mission['missingness'])):
        raise ValueError('source_unavailable')
    # The same bounded discovery owner already proved strict original root
    # provenance (including the current-DATA creation-publication join for a
    # DIRECT_NATIVE_CEO planning root). Generic Fabric may explicitly omit that
    # family's workstream projection and unrelated global dashboard inputs.
    # Those diagnostics stay visible; they cannot replace this exact owner join.
    root_rows = [row for row in roots['rows'] if row['job_id'] == selected['root_job_id']]
    origins = [row for row in roots['origins'] if row['root_job_id'] == selected['root_job_id']]
    if (len(root_rows) != 1 or len(origins) != 1
            or root_rows[0]['root_job_id'] != selected['root_job_id']
            or root_rows[0]['workstream'] != selected['work_ref']
            or origins[0]['work_ref'] != selected['work_ref']
            or creation != project['source_observation']['project_data']['creation_publication']):
        raise ValueError('source_unavailable')
    root_origin = digest(dict(root=root_rows[0], origin=origins[0], creation_publication=creation))
    document = project['control_room']
    rows = [row for row in document['autonomy']['responsibilities']
            if row.get('responsibility_ref') == selected['work_ref']]
    if len(rows) != 1 or not mw._qualified_current(validity=project['source_validity'],
            cache=project['cache_currentness'], responsibility=rows[0],
            responsibility_ref=selected['work_ref'], root_job_id=selected['root_job_id'],
            control_generated_at=document['generated_at'], autonomy_generated_at=document['autonomy']['generated_at']):
        raise ValueError('source_unavailable')
    # The complete original observation has already bound these raw inputs,
    # its exact creation publication and the canonical Runtime companion.
    return dict(schema='mastermind.project_help_execution_resource_read.v1' if execution_resource
            else 'mastermind.project_help_mission_read.v1',
        kind='CURRENT_DATA_EXECUTION_RESOURCE_READ' if execution_resource
            else 'CURRENT_DATA_CARD_WITH_UNOBSERVED_DISPATCH', selection=deepcopy(selected),
        owner_observation_sha256=digest(project['source_observation']),
        root_origin_sha256=root_origin, mission_read_state='PARTIAL',
        transport=deepcopy(transport), execution_authorized=False)

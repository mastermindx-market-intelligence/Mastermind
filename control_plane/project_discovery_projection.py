"""Request-local canonical DATA composition. Never a cache publication."""
from copy import deepcopy
import time

from common.executive_workspace_contract import digest
from control_plane.chairman_control_room import compose_control_room


def runtime_metadata(runtime, work_refs, *, creation_publications):
    """One bounded roots/origins metadata observation; no root detail fanout."""
    with runtime.observe_bounded_read() as read:
        discovered = read.discover_job_roots_bounded()
        if discovered.truncated or len(discovered.roots) > 64:
            raise ValueError('PROJECT_DISCOVERY_UNAVAILABLE')
        origins = read.classify_root_origins_bounded()
        roots = {root.job_id: root for root in discovered.roots}
        if len(roots) != len(discovered.roots) or {item.job_id for item in origins} != set(roots):
            raise ValueError('PROJECT_DISCOVERY_UNAVAILABLE')
        rows, proofs, history = [], [], {work: [] for work in work_refs}
        for origin in origins:
            if origin.kind == 'NON_CEO':
                continue
            provenance = origin.provenance
            if origin.kind not in {'STRICT_V2_CEO', 'LEGACY_CEO', 'DIRECT_NATIVE_CEO'} or type(provenance) is not dict:
                raise ValueError('PROJECT_DISCOVERY_UNAVAILABLE')
            work = provenance.get('workstream')
            if origin.kind == 'DIRECT_NATIVE_CEO':
                # The actual planning admission binds distinct Executive and
                # Workspace identities through its retained source publication;
                # their namespace hashes are intentionally not equated.
                creation = creation_publications.get(work)
                planning = provenance['direct_native'].get('project_planning')
                if creation is None or type(planning) is not dict:
                    continue
                expected = dict(request_id=creation['selection']['request_id'], principal_scope=creation['principal_scope'],
                    event_id=creation['event_id'], receipt_sha256=creation['receipt_sha256'])
                original_ws = [source for source in creation['sources'] if source['path'] == 'agentos/workstreams/WS-'+work[3:]+'.md']
                if (planning['publication'] != expected or len(original_ws) != 1
                        or any(planning['source'].get(key) != original_ws[0][key] for key in ('commit','path','content_sha256'))):
                    continue
            if work not in work_refs:
                continue
            root = roots[origin.job_id]
            if root.root_job_id != root.job_id or root.parent_job_id is not None:
                raise ValueError('PROJECT_DISCOVERY_UNAVAILABLE')
            rows.append(dict(job_id=root.job_id, root_job_id=root.root_job_id,
                workstream=work, status=root.status.value))
            proofs.append(dict(root_job_id=root.job_id, work_ref=work,
                creation_event_digest=origin.creation_event_digest))
            execution = origin.project_execution
            if execution is not None and (origin.kind != 'STRICT_V2_CEO' or execution['work_ref'] != work):
                raise ValueError('PROJECT_DISCOVERY_UNAVAILABLE')
            summary = None if execution is None else dict(
                operation_key=execution['operation_key'], command_id=execution['command_id'],
                continuation_mode=execution['continuation_mode'], source_sha256=digest(execution),
                context_sha256=execution['context_sha256'],
                input_reference_sha256=digest(execution['input_reference']),
                previous_root_job_id=None if execution['previous_run'] is None else execution['previous_run']['root_job_id'])
            history[work].append(dict(root_job_id=root.job_id, kind=origin.kind,
                purpose='PROJECT_EXECUTION' if execution is not None else
                    'PLANNING' if origin.kind == 'DIRECT_NATIVE_CEO' else 'ORCHESTRATION',
                status=root.status.value, creation_event_sha256=origin.creation_event_digest, execution=summary))
    receipt = read.receipt.to_dict()
    if receipt.get('state') != 'SAME':
        raise ValueError('PROJECT_DISCOVERY_UNAVAILABLE')
    material = dict(rows=sorted(rows, key=lambda item: item['job_id']),
        origins=sorted(proofs, key=lambda item: item['root_job_id']),
        history={work: sorted(items, key=lambda item: item['root_job_id']) for work, items in sorted(history.items())})
    return material, dict(receipt, snapshot_digest=digest(material))


def root_history(material, receipt, *, work_ref):
    """Project the original closed roots observation without choosing a root."""
    from common.project_execution_resource_contract import HISTORY_SCHEMA, validate_history
    roots = deepcopy(material['history'].get(work_ref, []))
    history = dict(schema=HISTORY_SCHEMA, work_ref=work_ref, roots=roots,
        observation=dict(receipt, snapshot_digest=digest(dict(work_ref=work_ref, roots=roots))))
    return validate_history(history, work_ref=work_ref)


def project_document(entry, runtime_rows):
    record = entry['record']
    generated = record['agent_os_state']['generated_at']
    work = record['selection']['work_ref']
    return compose_control_room(inbox=None, boot_packet=None, active_builds=None,
        agent_os_state=record['agent_os_state'], runtime_jobs=[row for row in runtime_rows if row['workstream'] == work],
        bindings=None, generated_at=generated)


def data_validity(document, entry, *, elapsed_ms):
    """Sample THAT canonical card's budgets; never refresh an old C card."""
    cards = []
    for row in document['autonomy']['responsibilities']:
        components = {}
        for name, meta in row.get('validity', {}).items():
            budget = meta.get('valid_for_ms')
            remaining = None if type(budget) is not int else max(0, min(budget - elapsed_ms, 15000 - elapsed_ms))
            components[name] = dict(proof_ref=meta.get('proof_ref'), qualified_at=meta.get('qualified_at'),
                remaining_ms=remaining, state='unqualified' if remaining is None else 'current' if remaining > 0 else 'stale')
        cards.append(dict(responsibility_ref=row['responsibility_ref'], root_job_id=row['root_job_id'], components=components))
    generation = entry['source_generation']
    return (dict(schema='mastermind.project_data_source_validity.v1', profile='workspace_project_data_read.v1',
        source_generation=generation, cards=cards), dict(state='fresh', source_generation=generation))


def compose_data_project(entry, *, runtime_rows, runtime_receipt, configured_observation,
        execution_resource=None):
    if execution_resource is not None:
        from common.project_execution_resource_contract import validate_resource
        selected = execution_resource['selection']
        validate_resource(execution_resource, **selected)
        if selected['work_ref'] != entry['record']['selection']['work_ref']:
            raise ValueError('PROJECT_DISCOVERY_UNAVAILABLE')
        selected_rows = [row for row in runtime_rows if row['job_id'] == selected['root_job_id']]
        if (len(selected_rows) != 1 or selected_rows[0]['workstream'] != selected['work_ref']
                or selected_rows[0]['root_job_id'] != selected['root_job_id']):
            raise ValueError('PROJECT_DISCOVERY_UNAVAILABLE')
        runtime_rows = selected_rows
    document = project_document(entry, runtime_rows)
    observed = entry['record']['observed_at_ms']
    elapsed = int(time.time() * 1000) - observed
    if not 0 <= elapsed < 15000:
        raise ValueError('PROJECT_DISCOVERY_UNAVAILABLE')
    validity, currentness = data_validity(document, entry, elapsed_ms=elapsed)
    basis = dict(source=deepcopy(entry['record']['source']), code_source=deepcopy(entry['record']['code_source']),
        data_observation=deepcopy(entry['data_observation']), creation_publication=deepcopy(entry['creation_publication']),
        source_generation=entry['source_generation'], document_digest=digest(document),
        source_validity_digest=digest(validity), cache_currentness_digest=digest(currentness))
    observation = dict(schema='mastermind.workspace_source_observation.v2', state='SAME', selection=None,
        control_room=deepcopy(configured_observation['control_room']), runtime=deepcopy(runtime_receipt), project_data=basis)
    if execution_resource is not None:
        observation.update(schema='mastermind.workspace_source_observation.v3',
            selection=deepcopy(execution_resource['selection']), resource=deepcopy(execution_resource))
    return dict(work_ref=entry['record']['selection']['work_ref'], control_room=document,
        source_validity=validity, cache_currentness=currentness, source_observation=observation)

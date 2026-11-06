"""Closed public safe summary of the actual basic ADOPT owner recipe.

No proof or permission is inferred from a preview or private-artifact locator.
The authenticated HTTP owner already binds original principal/request/witness.
"""
from control_plane.project_plan_adoption_git import validate_adoption_request


def validate_plan_adoption_preview(preview, request, selected):
    request = validate_adoption_request(request)
    if (type(selected) is not dict or set(selected) != {'schema','action','request_id','work_ref'}
            or selected['schema'] != 'mastermind.workspace_source_operation_lookup.v1'
            or selected['action'] != 'ADOPT_PLAN'
            or any(selected[key] != request[key] for key in ('request_id','work_ref'))
            or type(preview) is not dict or set(preview) != {'schema','work_ref','expected_commit',
                'expected_adoption','candidate_sha256','changed_frontmatter_fields','record_body_changed'}
            or preview['schema'] != 'mastermind.project_plan_adoption_preview.v1'
            or any(preview[key] != request[key] for key in ('work_ref','expected_commit','expected_adoption','candidate_sha256'))
            or type(preview['changed_frontmatter_fields']) is not list
            or any(type(key) is not str for key in preview['changed_frontmatter_fields'])
            or preview['changed_frontmatter_fields'] != sorted(set(preview['changed_frontmatter_fields']))
            or not set(preview['changed_frontmatter_fields']) <= {'waves','next_action'}
            or preview['record_body_changed'] is not False):
        raise ValueError('INVALID_PLAN_ADOPTION_PREVIEW')
    return preview

"""Fixed installed S24 owner, prepared only by the authenticated SAME-S19 seam.

No public request supplies basis/result/compiler/actor or source identity. The
Workspace action grant and original-source lifecycle remain independent owners.
"""
from control_plane.project_plan_proposal_operation import PreparedPlanProposal
from integrations.mastermind_workspace_app.project_plan_proposal_service import ProjectPlanProposalSourceOwner
from integrations.mastermind_workspace_app.project_journey_recipes import InstalledProjectPlanProposalRecipeAdapter
from integrations.mastermind_workspace_app.source_operation_principal import source_principal_scope


def build_installed_project_plan_proposal(*, events, private_inputs, contexts, journey, data, git_identity):
    def same_s19_only(*unused):
        raise ValueError('SAME_S19_PREPARATION_REQUIRED')

    def actor(principal):
        return {'principal_id':'workspace:'+source_principal_scope(principal)}

    def qualify(principal, prepared, recipe, phase):
        # The actual installed adapter already recompiled from its pinned code
        # closure. This fixed callback binds the actor/action/work/fingerprint;
        # it is neither an approval DTO nor a separate source-write grant.
        if type(prepared) is not PreparedPlanProposal or phase != 'PUBLICATION':
            return False
        payload=prepared.private_payload()
        return (payload['actor']==actor(principal)
            and payload['action']==recipe['action']=='publish_project_plan_proposal'
            and payload['request']['work_ref']==recipe['work_ref']
            and prepared.fingerprint_sha256==recipe['recipe_fingerprint_sha256'])

    return ProjectPlanProposalSourceOwner(events=events,private_inputs=private_inputs,
        permission_factory=contexts,adapter=InstalledProjectPlanProposalRecipeAdapter(journey),
        capture_basis=same_s19_only,capture_result=same_s19_only,actor_for=actor,
        qualify_recipe=qualify,publisher_binding=git_identity.binding,
        qualify_publisher=data.qualify_publisher,pr_owner=git_identity)

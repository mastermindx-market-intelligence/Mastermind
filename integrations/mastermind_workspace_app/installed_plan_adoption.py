"""Fixed installed ADOPT compiler, DATA, actor and basic-boundary composition.

The distinct source grant remains in the incumbent action owner. Captured
modules/observations do not grant publication; only the fixed Git publisher's
original command permit and exact default CAS may perform it. Status and
explicit observational recovery never acquire current Macro DATA here.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
from copy import deepcopy
import time

from control_plane.project_plan_adoption_compiler_source import capture_project_plan_adoption_compilers
from control_plane.project_plan_adoption_operation import PlanAdoptionRecipeAdapter, PreparedPlanAdoption
from control_plane.project_plan_adoption_basis import capture_plan_adoption_snapshot
from integrations.executive_mcp.installed import InstalledBootPacketCollector, _installed_child_env
from integrations.mastermind_workspace_app.canonical_project_data import InstalledCanonicalProjectData
from integrations.mastermind_workspace_app.source_operation_principal import source_principal_frame


def _fail():
    raise ValueError('PLAN_ADOPTION_INSTALLED_SOURCE_UNAVAILABLE')


class InstalledPlanAdoptionRecipes:
    def __init__(self, collector, data):
        if (type(collector) is not InstalledBootPacketCollector or collector._expected_source_sha is None
                or type(data) is not InstalledCanonicalProjectData or data.collector is not collector):
            _fail()
        self.collector, self.data = collector, data
        self.context = self._context()

    def _context(self):
        c = self.collector
        return (c, c._source_root, c._macro_root, c._code_root, c._python, c._runner,
            c._expected_source_sha, c._allow_synthetic_fixture,
            type(c)._snapshot_pair, type(c)._repository_observation_pair,
            self.data, self.data.context_binding())

    @contextmanager
    def capture(self, code_commit=None):
        if self._context() != self.context:
            _fail()
        c = self.collector
        env = _installed_child_env(code_root=c._code_root, macro_root=c._macro_root)
        before = c._snapshot_pair(env, deadline=time.monotonic() + 15)
        captured = capture_project_plan_adoption_compilers(macro_root=c._macro_root,
            expected_macro_sha=before[1], code_commit=before[1] if code_commit is None else code_commit,
            runner=c._runner)
        try:
            yield captured
        finally:
            captured.check()
            after = c._snapshot_pair(env, deadline=time.monotonic() + 15)
            if after != before or self._context() != self.context:
                _fail()

    def snapshot(self, request, principal, phase):
        with self.data.compilation_scope(principal, work_ref=request['work_ref']) as view:
            if view is None:
                _fail()
            return capture_plan_adoption_snapshot(view, request=request, phase=phase)

    def actor(self, principal, request, snapshot):
        subject = source_principal_frame(principal)['subject_digest']
        # The authenticated subject and original server clock, frozen once in
        # the existing private original-input artifact. No client actor/date.
        return {'principal_id': subject, 'decided_by': 'workspace-subject:' + subject,
            'decided_at': datetime.fromtimestamp(self._now(), timezone.utc).date().isoformat(),
            'decision_rationale': 'Explicit ADOPT_PLAN ' + request['request_id']
                + ' selected exact proposal ' + request['proposal_source']['content_sha256']
                + ' for ' + request['work_ref'] + '.'}

    def _now(self):
        return int(time.time())

    def qualifies(self, principal, prepared, recipe, phase):
        """Conservative basic ADOPT only; no scope/authority/body editor.

        The canonical compiler computes changes against the exact independently
        evolved CURRENT WS, not its historical adopted baseline. Phase two
        additionally enforces unchanged original CURRENT WS/proposal/predecessor
        and exact candidate publication before generating atomic DEC linkage.
        """
        if type(prepared) is not PreparedPlanAdoption or phase not in ('CANDIDATE', 'ADOPTION'):
            return False
        payload = prepared.private_payload()
        if payload['actor']['principal_id'] != source_principal_frame(principal)['subject_digest']:
            return False
        # The action owner just obtained this recipe through the exact nominal
        # installed adapter (prepare/restore recompile the original private
        # material first). This predicate is also invoked by every bounded
        # Git authorization guard: do not recapture/execute the compiler per
        # plumbing command. Those guards still check the actual distinct grant,
        # publisher qualification and exact command/phase/default CAS. No
        # caller supplies a recipe or a qualification flag.
        request = payload['request']
        if (recipe.get('schema') != 'agentos.plan_adoption_recipe.v1'
                or recipe.get('status') != 'PREVIEW_ONLY'
                or recipe.get('request_sha256') != prepared.fingerprint_sha256
                or any(recipe.get(key) != request[key] for key in ('request_id','work_ref','candidate_sha256'))):
            return False
        preview = recipe['preview']
        if (type(preview['changed_frontmatter_fields']) is not list
                or not set(preview['changed_frontmatter_fields']) <= {'waves', 'next_action'}
                or preview['record_body_changed'] is not False):
            return False
        if phase == 'CANDIDATE':
            return recipe['phase'] == 'CANDIDATE'
        # Only the real adapter's exact a5 decision recipe is supplied by the
        # action owner; repeated candidate qualification does not fabricate a
        # current source or prior-publication witness. Publisher CAS is final.
        return recipe['phase'] == 'ADOPTION_DECISION'


class InstalledPlanAdoptionRecipeAdapter:
    action = 'ADOPT_PLAN'
    def __init__(self, recipes):
        if type(recipes) is not InstalledPlanAdoptionRecipes:
            _fail()
        self._recipes = recipes

    @staticmethod
    def _inner(captured):
        return PlanAdoptionRecipeAdapter(compiler=captured.compiler, owner=captured.owner,
            source_binding=captured.source_binding)

    def prepare(self, *, request, initial_snapshot, actor):
        code = initial_snapshot['canonical_data']['executable_macro_commit']
        with self._recipes.capture(code) as captured:
            with captured._scope():
                return self._inner(captured).prepare(request=request,
                    initial_snapshot=initial_snapshot, actor=actor)

    def restore(self, *, private_payload, trusted_recipe_fingerprint):
        code = private_payload['source_binding']['compiler']['commit']
        with self._recipes.capture(code) as captured:
            with captured._scope():
                return self._inner(captured).restore(private_payload=private_payload,
                    trusted_recipe_fingerprint=trusted_recipe_fingerprint)

    def candidate_recipe(self, prepared):
        if type(prepared) is not PreparedPlanAdoption:
            _fail()
        code = prepared.private_payload()['source_binding']['compiler']['commit']
        with self._recipes.capture(code) as captured:
            with captured._scope():
                return self._inner(captured).candidate_recipe(prepared)

    def decision_recipe(self, prepared, *, current_snapshot, prior_qualified_publication):
        if type(prepared) is not PreparedPlanAdoption:
            _fail()
        code = prepared.private_payload()['source_binding']['compiler']['commit']
        with self._recipes.capture(code) as captured:
            with captured._scope():
                return self._inner(captured).decision_recipe(prepared,
                    current_snapshot=current_snapshot, prior_qualified_publication=prior_qualified_publication)


def build_plan_adoption_owner(*, collector, data, events, private_inputs, contexts, git_identity):
    from integrations.mastermind_workspace_app.project_plan_adoption_service import ProjectPlanAdoptionSourceOwner
    recipes = InstalledPlanAdoptionRecipes(collector, data)
    recipes._now = contexts._now
    return ProjectPlanAdoptionSourceOwner(events=events, private_inputs=private_inputs,
        permission_factory=contexts, adapter=InstalledPlanAdoptionRecipeAdapter(recipes),
        capture_snapshot=recipes.snapshot, actor_for=recipes.actor, qualify_recipe=recipes.qualifies,
        publisher_binding=git_identity.binding, qualify_publisher=data.qualify_publisher,
        pr_owner=git_identity)

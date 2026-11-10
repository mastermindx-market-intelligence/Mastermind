"""Lazy fixed canonical recipe composition inside the incumbent sealed owner.

No request supplies a compiler, module, path, principal, profile or Git owner.
The collector's actual repository/seal pair brackets capture AND every compile.
Status/reconciliation need not acquire this source; only original preparation
or restoration explicitly enters it. No receipt here grants a source write.
"""
from contextlib import contextmanager
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import time

from control_plane.project_planning_compiler_source import capture_project_planning_compilers
from integrations.executive_mcp.installed import InstalledBootPacketCollector, _installed_child_env
from integrations.mastermind_workspace_app.project_creation_operation import ProjectCreationRecipeAdapter, PreparedProjectCreation
from integrations.mastermind_workspace_app.project_profiles import validate_profiles, profile_choices
from control_plane.project_plan_proposal_operation import PlanProposalRecipeAdapter
from control_plane.ceo_boot_packet import bounded_subprocess_runner

_PROFILE_PATH = 'config/workspace_project_authoring_profiles.json'


def _fail():
    raise ValueError('PROJECT_JOURNEY_SOURCE_UNAVAILABLE')


class InstalledProjectJourneyRecipes:
    def __init__(self, collector):
        if type(collector) is not InstalledBootPacketCollector or collector._expected_source_sha is None:
            _fail()
        self.collector = collector
        self.context = self._context()

    def _context(self):
        c = self.collector
        return (c, c._source_root, c._macro_root, c._code_root, c._python,
                c._expected_source_sha, c._allow_synthetic_fixture,
                type(c)._snapshot_pair, type(c)._repository_observation_pair)

    @contextmanager
    def capture(self, code_commit=None):
        if self._context() != self.context:
            _fail()
        c = self.collector
        env = _installed_child_env(code_root=c._code_root, macro_root=c._macro_root)
        before = c._snapshot_pair(env, deadline=time.monotonic() + 15)
        code = before[1] if code_commit is None else code_commit
        captured = capture_project_planning_compilers(macro_root=c._macro_root,
            expected_macro_sha=before[1], code_commit=code, runner=c._runner)
        try:
            yield captured, before
        finally:
            captured.check()
            after = c._snapshot_pair(env, deadline=time.monotonic() + 15)
            if after != before or self._context() != self.context:
                _fail()

    def profiles(self, source_sha):
        c = self.collector
        result = c._runner(['git','--no-optional-locks','--no-replace-objects','-C',str(c._source_root),
            'show',source_sha+':'+_PROFILE_PATH],cwd=c._source_root,timeout=5,max_bytes=32768,
            env=_installed_child_env(code_root=c._code_root,macro_root=c._macro_root))
        if (type(result) is not dict or result.get('code') != 0 or type(result.get('stdout')) is not str
                or any(result.get(k) is True for k in ('timed_out','limit_exceeded','invalid_utf8'))):
            _fail()
        def unique(pairs):
            value = {}
            for key,item in pairs:
                if key in value: _fail()
                value[key] = item
            return value
        return validate_profiles(json.loads(result['stdout'],object_pairs_hook=unique))

    def options(self):
        with self.capture() as (captured, before):
            catalogue = self.profiles(before[0])
            return dict(schema='mastermind.project_creation_options.v1',expected_macro_sha=before[1],
                profiles=profile_choices(catalogue),grounding={'mastermind_sha':before[0],'macro_sha':before[1]})


class InstalledProjectCreationRecipeAdapter:
    def __init__(self, recipes):
        if type(recipes) is not InstalledProjectJourneyRecipes: _fail()
        self._recipes = recipes

    def _inner(self, captured, profiles):
        return ProjectCreationRecipeAdapter(captured.creation_compiler, set(captured.programs),
            profiles, captured.creation_source_binding)

    def prepare(self, *, request, principal):
        with self._recipes.capture() as (captured, before):
            profiles = self._recipes.profiles(before[0])
            with captured._scope():
                return self._inner(captured,profiles).prepare(request=request,principal=principal)

    def restore(self, *, private_payload, trusted_recipe_fingerprint, principal):
        # Original private source refs, not public request paths, select the
        # recorded compiler revision. The actual capture still proves ancestry.
        code = private_payload['source_binding']['compiler']['commit']
        with self._recipes.capture(code) as (captured, before):
            profiles = private_payload['initial_snapshot']['profiles']
            with captured._scope():
                return self._inner(captured,profiles).restore(private_payload=private_payload,
                    trusted_recipe_fingerprint=trusted_recipe_fingerprint,principal=principal)

    def proposal_recipe(self, prepared):
        if type(prepared) is not PreparedProjectCreation: _fail()
        payload = prepared.private_payload()
        with self._recipes.capture(payload['source_binding']['compiler']['commit']) as (captured, before):
            with captured._scope():
                return self._inner(captured,payload['initial_snapshot']['profiles']).proposal_recipe(prepared)


class InstalledProjectPlanProposalRecipeAdapter:
    action = 'publish_project_plan_proposal'
    def __init__(self, recipes):
        if type(recipes) is not InstalledProjectJourneyRecipes: _fail()
        self._recipes = recipes

    def prepare(self, *, request, initial_snapshot, actor, qualified_result):
        with self._recipes.capture() as (captured,before):
            with captured._scope():
                adapter = PlanProposalRecipeAdapter(compiler=captured.proposal_compiler,owner=captured.owner,
                    declaration=captured.declaration,source_binding=captured.proposal_source_binding)
                return adapter.prepare(request=request,initial_snapshot=initial_snapshot,
                    actor=actor,qualified_result=qualified_result)

    def restore(self, *, private_payload, trusted_recipe_fingerprint):
        with self._recipes.capture(private_payload['source_binding']['compiler']['commit']) as (captured,before):
            with captured._scope():
                adapter = PlanProposalRecipeAdapter(compiler=captured.proposal_compiler,owner=captured.owner,
                    declaration=captured.declaration,source_binding=captured.proposal_source_binding)
                return adapter.restore(private_payload=private_payload,trusted_recipe_fingerprint=trusted_recipe_fingerprint)

    def _prepare_observed(self, *, request, initial_snapshot, actor, qualified_result, observation):
        # Same full installed compiler acquisition/checks; only the surrounding
        # fixed service's nominal lexical observation supplies result DATA.
        with self._recipes.capture() as (captured,before):
            with captured._scope():
                adapter = PlanProposalRecipeAdapter(compiler=captured.proposal_compiler,owner=captured.owner,
                    declaration=captured.declaration,source_binding=captured.proposal_source_binding)
                return adapter._prepare_observed(request=request,initial_snapshot=initial_snapshot,
                    actor=actor,qualified_result=qualified_result,observation=observation)

    def recipe(self, prepared):
        payload = prepared.private_payload()
        with self._recipes.capture(payload['source_binding']['compiler']['commit']) as (captured,before):
            with captured._scope():
                return PlanProposalRecipeAdapter(compiler=captured.proposal_compiler,owner=captured.owner,
                    declaration=captured.declaration,source_binding=captured.proposal_source_binding).recipe(prepared)

import unittest
from dataclasses import replace
from integrations.session_bridge.t3_mission_brief import MissionBrief,Phase


def brief():
    return MissionBrief('native-task','Implement scoped feature','https://github.com/example/repo/blob/'+'a'*40+'/docs/brief.md','a'*40,
        (Phase('build','Build once',('focused tests',)),Phase('verify','Verify original user journey',('consumer proof',))),
        ('Real user workflow works','Source saved'),('src/feature.py',),('No unrelated refactor',),
        ('Permission missing','Unknown original effect'), 'github:example/repo/docs/notes.json','existing-approved-envelope')


class MissionTests(unittest.TestCase):
    def test_complete_scope_survives_render(self):
        s=brief().render()
        for text in ('DONE_WHEN','Capacity Fabric','CAS-protected','next safe','not grant','No unrelated refactor','src/feature.py'):self.assertIn(text,s)

    def test_fingerprint_changes_with_scope(self):
        self.assertNotEqual(brief().fingerprint,replace(brief(),done_when=('Different scope',)).fingerprint)

    def test_phase_completion_is_not_acceptance(self):
        b=brief();c=b.checkpoint(completed_phases=('build',),next_action='Run consumer proof',evidence=('tests passed',),remaining=('consumer proof not run',))
        self.assertFalse(c['accepted']);self.assertEqual(c['brief_sha256'],b.fingerprint)

    def test_checkpoint_preserves_uncertain_effects(self):
        c=brief().checkpoint(completed_phases=(),next_action='Reconcile original operation',evidence=('transport lost',),remaining=('all acceptance',),unknown_effects=('original request a',))
        self.assertEqual(c['unresolved_original_effects'],['original request a'])

    def test_unknown_phase_refused(self):
        with self.assertRaises(ValueError):brief().checkpoint(completed_phases=('invented',),next_action='x',evidence=('x',),remaining=('x',))

    def test_no_empty_done_when(self):
        with self.assertRaises(ValueError):replace(brief(),done_when=())

    def test_no_mutable_phases(self):
        with self.assertRaises(ValueError):replace(brief(),phases=list(brief().phases))

    def test_no_duplicate_phases(self):
        with self.assertRaises(ValueError):replace(brief(),phases=(brief().phases[0],)*2)

    def test_no_unpinned_source(self):
        with self.assertRaises(ValueError):replace(brief(),source_ref='https://github.com/example/repo/blob/main/brief.md')

    def test_no_traversal_scope(self):
        for path in ('../other','/etc/config','.git/config','src/**','src/a b.py'):
            with self.subTest(path=path),self.assertRaises(ValueError):replace(brief(),allowed_write_paths=(path,))

    def test_no_secret_in_objective(self):
        with self.assertRaises(ValueError):replace(brief(),objective='Bearer '+'a'*30)

    def test_checkpoint_needs_remaining_ruler(self):
        with self.assertRaises(ValueError):brief().checkpoint(completed_phases=('build',),next_action='done',evidence=('x',),remaining=())


if __name__=='__main__':unittest.main()

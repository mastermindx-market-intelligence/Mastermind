"""Exact three-generation validation; inert fixtures, never transport or export."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

SOURCE = Path(sys.argv.pop(1)).resolve()
LEGACY = Path('/Volumes/Mastermind/agent-workspaces/claude/44ff44e73b840f81/fabric-start-publication-20261012-fb76f8a5c8c5e179/integrations/session_bridge/original_validator_compat/test_collector_validator_compat.py')
saved = sys.argv[:]
sys.argv = [str(LEGACY), str(SOURCE)]
spec = importlib.util.spec_from_file_location('legacy_fixture', LEGACY)
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)
sys.argv = saved
delivery, collector = fixture.delivery, fixture.collector
E126 = 'e126d6432135725a7a7846cbe9f9749305dfe9dd7cfe37037fc413a1136248bf'
LATEST = '0be15bd5d3304a65673576fd30386bcc977c02ed8ee28313a4cb1ed454f8c409'
E126_PATH = fixture.ORIGINAL_PATH.with_name('artifact_production.e126d643.before.py')


class AdoptionTests(unittest.TestCase):
    # Reuse only fixture utilities; legacy test cases run separately once.
    setUp = fixture.VersionBoundCollectorTests.setUp
    replace_support = fixture.VersionBoundCollectorTests.replace_support
    response = fixture.VersionBoundCollectorTests.response
    context = fixture.VersionBoundCollectorTests.context

    def generation(self, sha):
        self.files[str(E126_PATH)] = self.future
        assert fixture.digest(self.future) == E126
        latest = (SOURCE / 'artifact_production.py').read_bytes()
        assert fixture.digest(latest) == LATEST
        self.files[str(delivery.HERE / 'artifact_production.py')] = latest
        self.replace_support({**self.manifest, 'artifact_production.py': sha})

    def test_new_generation_uses_matching_installed_validator(self):
        self.generation(LATEST)
        self.assertIsNone(self.context())
        request, _, _, response, expected = self.response('expanded')
        self.assertEqual(collector.validate_response(response, request, 'glm')[2], expected)

    def test_previous_generation_remains_readable_after_adoption(self):
        self.generation(E126)
        context = self.context()
        self.assertIsNotNone(context)
        self.assertIn(str(E126_PATH), self.reads)
        request, _, _, response, expected = self.response('expanded')
        self.assertEqual(collector.validate_response(response, request, 'glm', original_validator=context)[2], expected)

    def test_oldest_generation_keeps_its_original_grammar(self):
        self.generation(fixture.ORIGINAL_SHA)
        context = self.context()
        request, _, _, response, expected = self.response('whole')
        self.assertEqual(collector.validate_response(response, request, 'glm', original_validator=context)[2], expected)
        request, _, _, response, _ = self.response('expanded')
        with self.assertRaises(ValueError):
            collector.validate_response(response, request, 'glm', original_validator=context)

    def test_pre_adoption_e126_keeps_default_path_without_snapshot(self):
        self.generation(E126)
        self.files[str(delivery.HERE / 'artifact_production.py')] = self.future
        self.files.pop(str(E126_PATH))
        self.assertIsNone(self.context())

    def test_latest_requires_actual_matching_installation(self):
        self.generation(LATEST)
        for raw in (self.future, self.original, b'unknown source'):
            self.files[str(delivery.HERE / 'artifact_production.py')] = raw
            with self.subTest(sha=fixture.digest(raw)), self.assertRaises(ValueError): self.context()

    def test_unknown_manifest_never_executes_source(self):
        self.generation('f' * 64)
        with patch.object(delivery, '_original_validator_source') as source, self.assertRaises(ValueError):
            self.context()
        source.assert_not_called()

    def test_e126_missing_or_drifted_snapshot_refuses_before_transport(self):
        self.generation(E126)
        for raw in (None, self.future + b'\n', self.original):
            if raw is None: self.files.pop(str(E126_PATH), None)
            else: self.files[str(E126_PATH)] = raw
            with self.subTest(raw=raw is None), patch.object(delivery, 'transport') as transport:
                with self.assertRaises((ValueError, OSError)):
                    collector.collect(self.binding_path, run_id=fixture.RUN, root=fixture.ROOT,
                                      parent=fixture.PARENT, destination=SOURCE / 'NEVER_CREATED')
                transport.assert_not_called()
        self.assertFalse((SOURCE / 'NEVER_CREATED').exists())

    def test_e126_rechecks_snapshot_and_reader_on_every_operation(self):
        self.generation(E126)
        context = self.context()
        for path in (E126_PATH, delivery.HERE / 'artifact_reader.py'):
            before = self.files[str(path)]
            self.files[str(path)] += b'\n'
            for operation in (lambda: context.parse_packet(self.files[str(self.packet_path)].decode()),
                              lambda: context.validate_contract(self.contract),
                              lambda: context.paths(self.contract),
                              lambda: context.manifest_from_stdout('', root=fixture.ROOT,
                                  parent=fixture.PARENT, run_id=fixture.RUN, host=fixture.HOST)):
                with self.subTest(path=str(path)), self.assertRaises(ValueError): operation()
            self.files[str(path)] = before

    def test_e126_context_cannot_consume_other_generation_contract(self):
        self.generation(E126)
        context = self.context()
        for other in (fixture.ORIGINAL_SHA, LATEST):
            self.replace_support({**self.manifest, 'artifact_production.py': other})
            with self.subTest(other=other), self.assertRaisesRegex(ValueError, 'original_support_mismatch'):
                context.parse_packet(self.files[str(self.packet_path)].decode())

    def test_context_cannot_rebind_generation_or_mutate_installed_module(self):
        self.generation(E126)
        context = self.context()
        before = dict(vars(fixture.future))
        for name, value in (('_producer_sha', LATEST), ('_support_digest', 'f' * 64), ('source_path', E126_PATH)):
            with self.subTest(name=name), self.assertRaises(AttributeError): setattr(context, name, value)
        context.validate_contract(self.contract)
        self.assertEqual(before, vars(fixture.future))

    def test_current_source_drift_cannot_be_reclassified_as_e126_history(self):
        self.generation(E126)
        self.files[str(delivery.HERE / 'artifact_production.py')] += b'\n'
        with self.assertRaises(ValueError): self.context()

    def test_seal_transcript_is_not_duplicate_final_but_duplicate_final_refuses(self):
        self.generation(E126)
        context = self.context()
        _, stdout, _, _, expected = self.response('expanded')
        text = 'FABRIC_ARTIFACT_SEAL_V1 ' + json.dumps(expected) + '\n' + stdout.decode()
        scope = dict(root=fixture.ROOT, parent=fixture.PARENT, run_id=fixture.RUN, host=fixture.HOST)
        self.assertEqual(context.manifest_from_stdout(text, **scope), expected)
        with self.assertRaises(ValueError): context.manifest_from_stdout(text + '\n' + stdout.decode(), **scope)


if __name__ == '__main__': unittest.main()

"""Typed Codex diagnostics and opaque malformed Claude capture retention."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'candidate'),str(ROOT/'source')]
import provider_outcome as outcome

class Capture(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.home=Path(temp.name)
        (self.home/'sessions').mkdir()
        self.path=self.home/'sessions'/'one.jsonl'

    def parse(self,info,prior=None):
        events=[dict(type='session_meta',payload={'id':'fixture-session'})]
        if prior:events.append(prior)
        events.append(dict(type='event_msg',payload=dict(type='error',codex_error_info=info,message='quota is not parsed here')))
        self.path.write_text(''.join(json.dumps(e)+'\n' for e in events))
        return outcome.parse_codex(self.home,1,b'')

    def test_capacity_enums_distinct_from_task_budget_context_and_auth(self):
        for enum,kind in {'usage_limit_exceeded':'quota_exhausted','rate_limit_exceeded':'rate_limit',
            'session_budget_exceeded':'budget_limit','context_window_exceeded':'context_limit',
            'unauthorized':'authentication','too_many_denials':'permission',
            'UnknownFutureVariant':'unknown'}.items():
            with self.subTest(enum=enum):
                row=self.parse(enum)
                self.assertEqual(row['kind'],kind)
                self.assertEqual(row['initial_rejection'],kind in outcome.CAPACITY)

    def test_prior_model_tool_or_completed_turn_withholds_replay(self):
        for prior in [dict(type='response_item',payload=dict(type='message',role='assistant',content=[])),
            dict(type='response_item',payload=dict(type='function_call',name='exec_command')),
            dict(type='event_msg',payload=dict(type='task_complete')),
            dict(type='future_event',payload={})]:
            with self.subTest(prior=prior):
                self.assertFalse(self.parse('usage_limit_exceeded',prior)['initial_rejection'])

    def test_empty_ambiguous_and_malformed_rollouts_never_succeed(self):
        self.path.write_text('')
        self.assertEqual(outcome.parse_codex(self.home,0,b'')['kind'],'unknown')
        self.path.write_text('{broken')
        with self.assertRaises(ValueError):outcome.parse_codex(self.home,1,b'')
        (self.home/'sessions'/'two.jsonl').write_text('{}')
        with self.assertRaisesRegex(ValueError,'single_session'):outcome.parse_codex(self.home,1,b'')

    def test_malformed_private_stream_preserved_but_not_echoed(self):
        source=self.home/'raw-temp'
        raw=b'{"private_reasoning":"private fixture"}\n{broken'
        source.write_bytes(raw)
        display,fields,_=outcome.parse_claude(raw,1)
        self.assertEqual(display,'');self.assertEqual(fields['kind'],'unknown')
        target=self.home/'run.provider.json'
        index=outcome.retain_capture(source,target)
        saved=self.home/index['file']
        self.assertEqual(saved.read_bytes(),raw)
        self.assertEqual(saved.stat().st_mode & 0o777,0o600)
        self.assertEqual(index['sha256'],hashlib.sha256(raw).hexdigest())
        self.assertFalse(source.exists());self.assertFalse(index['truncated'])

if __name__=='__main__':unittest.main()

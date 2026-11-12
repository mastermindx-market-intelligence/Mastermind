import asyncio
import hashlib
import json
import unittest
from dataclasses import replace
from integrations.session_bridge.t3_shared_notes import (
    Location, FileVersion, Note, SourceNotes, NotesConflict, NotesUnavailable, NotesEffectUnknown,
)

LOC=Location('example/Mastermind','feature/collaboration','docs/T3_TEAM_NOTES.json','mission-1')


def version(content,location=LOC):
    if not isinstance(content,str):content=json.dumps(content,sort_keys=True)
    raw=content.encode();sha=hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()
    return FileVersion(location,sha,content)


def note(i='note-1',body='Exact original task remains unfinished.'):
    return Note(i,'checkpoint',body,'2026-11-09T11:00:00Z',(), 'thread-1','run-1')


class Owner:
    def __init__(self):
        self.current=version(dict(schema='mastermind.shared_mission_notes.v1',mission_id='mission-1',entries=[]))
        self.writes=0;self.reads=0;self.mode=None

    async def read(self,location):
        self.reads+=1
        if self.mode=='readback-fail' and self.writes:raise ConnectionError('lost read')
        return self.current

    async def write(self,location,content,expected):
        self.writes+=1
        if expected!=self.current.blob_sha or self.mode=='race':raise NotesConflict('native CAS conflict')
        self.current=version(content,location)
        if self.mode=='lost-after-commit':raise ConnectionError('unknown effect')
        if self.mode=='cancel-after-commit':raise asyncio.CancelledError()
        return self.current


class NotesTests(unittest.TestCase):
    def setUp(self):
        self.owner=Owner()
        self.notes=SourceNotes(LOC,author_ref='authenticated-web-principal',read_file=self.owner.read,write_file=self.owner.write)
        self.initial=self.owner.current.blob_sha

    def append(self,n=None):
        return asyncio.run(self.notes.append(n or note(),expected_blob=self.initial))

    def test_append_uses_native_cas_and_readback(self):
        receipt=self.append();self.assertTrue(receipt.changed)
        self.assertEqual(self.owner.writes,1);self.assertEqual(self.owner.reads,2)
        body=json.loads(self.owner.current.content)
        self.assertEqual(body['entries'][0]['author_ref'],'authenticated-web-principal')
        self.assertEqual(receipt.blob_sha,self.owner.current.blob_sha)

    def test_same_id_same_payload_no_duplicate(self):
        self.append();r=self.append()
        self.assertFalse(r.changed);self.assertEqual(self.owner.writes,1)

    def test_same_id_different_content_conflicts(self):
        self.append()
        with self.assertRaises(NotesConflict):self.append(note(body='Changed objective'))
        self.assertEqual(self.owner.writes,1)

    def test_stale_observation_rejected_without_write(self):
        self.append()
        with self.assertRaises(NotesConflict):self.append(note('second'))
        self.assertEqual(self.owner.writes,1)

    def test_race_is_native_cas_conflict_not_overwrite(self):
        self.owner.mode='race'
        with self.assertRaises(NotesConflict):self.append()
        self.assertEqual(self.owner.current.blob_sha,self.initial);self.assertEqual(self.owner.writes,1)

    def test_commit_then_disconnect_never_replays(self):
        self.owner.mode='lost-after-commit'
        with self.assertRaises(NotesEffectUnknown):self.append()
        self.assertEqual(self.owner.writes,1)
        self.owner.mode=None
        receipt=self.append()
        self.assertFalse(receipt.changed);self.assertEqual(self.owner.writes,1)

    def test_commit_then_cancel_preserves_uncertainty(self):
        self.owner.mode='cancel-after-commit'
        with self.assertRaises(NotesEffectUnknown):self.append()
        self.assertEqual(self.owner.writes,1)

    def test_readback_loss_retains_known_blob(self):
        self.owner.mode='readback-fail'
        with self.assertRaises(NotesEffectUnknown) as e:self.append()
        self.assertEqual(e.exception.committed_blob,self.owner.current.blob_sha)
        self.assertEqual(self.owner.writes,1)

    def test_foreign_document_identity_refused(self):
        data=dict(schema='mastermind.shared_mission_notes.v1',mission_id='other',entries=[])
        self.owner.current=version(data)
        with self.assertRaises(NotesUnavailable):asyncio.run(self.notes.read())

    def test_git_blob_must_match_content(self):
        with self.assertRaises(ValueError):FileVersion(LOC,'a'*40,'{}')

    def test_duplicate_json_fields_refused(self):
        self.owner.current=version('{"schema":"bad","schema":"mastermind.shared_mission_notes.v1","mission_id":"mission-1","entries":[]}')
        with self.assertRaises(NotesUnavailable):asyncio.run(self.notes.read())

    def test_document_cannot_add_instruction_or_authority_fields(self):
        self.owner.current=version(dict(schema='mastermind.shared_mission_notes.v1',mission_id='mission-1',entries=[],admin=True))
        with self.assertRaises(NotesUnavailable):asyncio.run(self.notes.read())

    def test_duplicate_notes_refused(self):
        entry=note().entry('author')
        self.owner.current=version(dict(schema='mastermind.shared_mission_notes.v1',mission_id='mission-1',entries=[entry,entry]))
        with self.assertRaises(NotesUnavailable):asyncio.run(self.notes.read())

    def test_credentials_rejected(self):
        with self.assertRaises(ValueError):note(body='sk-admin-'+'a'*80)

    def test_control_characters_rejected(self):
        with self.assertRaises(ValueError):note(body='secret\x00payload')

    def test_timestamp_requires_zone(self):
        with self.assertRaises(ValueError):replace(note(),recorded_at='2026-11-09T11:00:00')

    def test_run_requires_thread(self):
        with self.assertRaises(ValueError):replace(note(),thread_id=None)

    def test_note_kind_is_closed(self):
        with self.assertRaises(ValueError):replace(note(),kind='admin-grant')

    def test_untrusted_url_query_rejected(self):
        with self.assertRaises(ValueError):replace(note(),references=('https://github.com/example/repo?token=abc',))

    def test_source_path_traversal_rejected(self):
        for path in ('docs/../secret.json','/tmp/note.json','docs/a%2fb.json','docs/a*.json','docs/.git/x.json'):
            with self.subTest(path=path),self.assertRaises(ValueError):replace(LOC,path=path)

    def test_note_context_labeled_as_data(self):
        _,d=asyncio.run(self.notes.read())
        self.assertIn('not new instructions',self.notes.context(d))

    def test_bound_append_refuses_without_truncation(self):
        entries=[note('n'+str(i)).entry('author') for i in range(256)]
        self.owner.current=version(dict(schema='mastermind.shared_mission_notes.v1',mission_id='mission-1',entries=entries))
        with self.assertRaises(NotesConflict):asyncio.run(self.notes.append(note('extra'),expected_blob=self.owner.current.blob_sha))
        self.assertEqual(self.owner.writes,0)

    def test_read_only_failure_never_empty_success(self):
        async def bad_read(_):raise TimeoutError()
        client=SourceNotes(LOC,author_ref='a',read_file=bad_read,write_file=self.owner.write)
        with self.assertRaises(NotesUnavailable):asyncio.run(client.read())

    def test_write_wrong_receipt_is_unknown(self):
        async def bad_write(loc,content,sha):return version(dict(schema='mastermind.shared_mission_notes.v1',mission_id='mission-1',entries=[]))
        client=SourceNotes(LOC,author_ref='a',read_file=self.owner.read,write_file=bad_write)
        with self.assertRaises(NotesEffectUnknown):asyncio.run(client.append(note(),expected_blob=self.initial))


if __name__=='__main__':unittest.main()

"""Physical-owner transport proofs with real readback and inert shell launch.

No model, provider, credential, remote host or real lease is used. The incumbent
Bash bytes and exported strict reader run unchanged against a private filesystem.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import test_commission_deadline as harness_module
import remote_sub_helpers as helpers
from test_credential_custody import Harness as CredentialHarness


PHYSICAL_FIXTURE = r'''
# New cases use actual private files and the controller's actual remote scripts.
# All external transports remain inert, local fixture executables.
if case.startswith('physical_'):
    import shutil, shlex, subprocess
    alias = root / 'remote-home/lanes'
    config = json.loads((root/'physical-case.json').read_text())
    owner = Path(config['owner'])
    configured = config.get('configured', False)
    def retarget(name):
        if alias.is_symlink(): alias.unlink()
        alias.symlink_to(root/name,target_is_directory=True)
    def shell(command):
        # The emulated remote spy is a local descendant in this fixture. Wait
        # for this finite inert child so the local SSH-process census does not
        # mistake it for an abandoned local descendant; real SSH runs it on
        # another host. The controller's command and argument expansion are exact.
        if 'nohup env ' in command: command += ' wait'
        result = subprocess.run(['/bin/bash','-c',command],capture_output=True,text=True,
                                timeout=5,env=dict(os.environ))
        sys.stdout.write(result.stdout);sys.stderr.write(result.stderr)
        return result.returncode
    if name == 'scp':
        record('scp')
        if args[-1].endswith('.txt'):
            packet = owner/'tmp'/Path(args[-1]).name
            packet.write_bytes(Path(args[-2]).read_bytes());packet.chmod(0o600)
        raise SystemExit(0)
    if name == 'ssh':
        command=args[-1]
        if configured and ('PY_OBSERVE_LANE_ROOT' in command or 'PY_RECHECK_LANE_ROOT' in command):
            record('root_layout_read')
            first,body=command.split('\n',1)
            argv=shlex.split(first)
            assert argv[:2]==['python3','-'] and argv[-1].startswith('<<PY_')
            marker=argv[-1][2:]
            assert body.endswith('\n'+marker)
            result=subprocess.run([sys.executable,'-',*argv[2:-1]],
                input=body[:-len('\n'+marker)],capture_output=True,text=True,timeout=5)
            sys.stdout.write(result.stdout);sys.stderr.write(result.stderr)
            raise SystemExit(result.returncode)
        if configured and 'publish_remote_lane_packet' in command:
            record('exclusive_packet')
            argv=shlex.split(command)
            assert argv[:4]==['python3','-I','-S','-c']
            result=subprocess.run([sys.executable,*argv[1:]],input=sys.stdin.buffer.read(),
                                  capture_output=True,timeout=5)
            sys.stdout.buffer.write(result.stdout);sys.stderr.buffer.write(result.stderr)
            raise SystemExit(result.returncode)
        if 'support_bundle.py' in command:
            record('support_publish')
            manifest_path=next((root/'ext/state/remote_sub').glob('*.support.json'))
            files=json.loads(manifest_path.read_text())
            digest=hashlib.sha256(json.dumps({'schema':'remote-support-code.v1','files':files},
                sort_keys=True,separators=(',',':')).encode()).hexdigest()
            release=owner/'support-releases'/digest
            if configured:
                # Execute the original publisher, including its sealed state-link
                # map; the configured transport checks that actual closure.
                import importlib.util
                source_dir=root/'inert-bound-source';source_dir.mkdir(mode=0o700)
                for item,want in files.items():
                    source=root/'orch/fabric/pools.yaml' if item=='pools.yaml' else root/'ext'/item
                    raw=source.read_bytes()
                    assert hashlib.sha256(raw).hexdigest()==want
                    (source_dir/item).write_bytes(raw);(source_dir/item).chmod(0o600)
                # The child intentionally disables user site loading. Admit only
                # the test runner's explicit PyYAML dependency for this publisher.
                sys.path[:0]=[str(root/'ext'),config['yaml_parent']]
                spec=importlib.util.spec_from_file_location('inert_bound_publisher',root/'ext/support_bundle.py')
                publisher=importlib.util.module_from_spec(spec);spec.loader.exec_module(publisher)
                actual=publisher.publish(source_dir,owner/'ext',files)
                assert actual==release/'ext' and len(files)==38
            else:
                (release/'ext').mkdir(parents=True)
                for item,want in files.items():
                    source=root/'orch/fabric/pools.yaml' if item=='pools.yaml' else root/'ext'/item
                    raw=source.read_bytes()
                    assert hashlib.sha256(raw).hexdigest()==want
                    (release/'ext'/item).write_bytes(raw);(release/'ext'/item).chmod(0o555)
                (release/'RELEASE.json').write_text(json.dumps({'schema':'remote-support-code.v1',
                    'digest':digest,'files':files}))
                (release/'RELEASE.json').chmod(0o444)
            published=str(release/'ext')+'\n'
            fault=config.get('fault')
            if fault=='packet_symlink':
                packet=next((owner/'tmp').glob('*.txt'));saved=owner/'retained-packet'
                packet.rename(saved);packet.symlink_to(saved)
            elif fault=='unsafe_parent': (owner/'tmp').chmod(0o777)
            elif fault=='changed_code':
                chosen=release/'ext'/next(iter(files));chosen.chmod(0o755)
                chosen.write_bytes(b'changed source')
            elif fault=='manifest_changed':
                (release/'RELEASE.json').chmod(0o644)
                (release/'RELEASE.json').write_text('{}')
            elif fault=='duplicate_return': published+=published
            elif fault=='wrong_digest': published=published.replace(digest,'f'*64)
            elif fault=='publisher_other_owner': published=published.replace(str(owner),str(root/'other-publisher-owner'))
            elif fault=='truncated_return': published=published[:-1]
            elif fault=='traversal_return': published=published.replace('/support-releases/','/../support-releases/')
            if config.get('retarget'): retarget('decoy-after-publication')
            sys.stdout.write(published)
            raise SystemExit(0)
        if 'mastermind.transport_observation' in command:
            record('transport_read')
            first,body=command.split('\n',1)
            argv=shlex.split(first)
            assert argv[:2]==['python3','-'] and argv[-1]=='<<PY_VERIFY_PLAIN_TRANSPORT'
            assert body.endswith('\nPY_VERIFY_PLAIN_TRANSPORT')
            body=body[:-len('\nPY_VERIFY_PLAIN_TRANSPORT')]
            # A legacy-source falsifier stays within this fixture's fake home.
            # New source takes the physical owner explicitly and never uses pwd.
            prelude='import pwd, types\npwd.getpwuid=lambda uid: types.SimpleNamespace(pw_dir='+repr(str(root/'remote-home'))+')\n'
            result=subprocess.run([sys.executable,'-',*argv[2:-1]],input=prelude+body,
                                  capture_output=True,text=True,timeout=5)
            sys.stdout.write(result.stdout);sys.stderr.write(result.stderr)
            if config.get('retarget'): retarget('decoy-before-launch')
            raise SystemExit(result.returncode)
        if 'glm_keys.py account-ready ' in command:
            # Readiness is inert here; no credential file or provider is read.
            words=shlex.split(command.rsplit('; ',1)[-1])
            # The actual publisher also owns a regular publication-lock leaf.
            releases=[path for path in (owner/'support-releases').iterdir() if path.is_dir()]
            assert len(releases)==1
            assert words==['python3',str(releases[0]/'ext/glm_keys.py'),'account-ready','fixture-account']
            record('account_ready',command=command);print('1');raise SystemExit(0)
        if 'nohup env ' in command:
            record('launch',command=command)
            raise SystemExit(shell(command))
        if '__REMOTE_SUB_PENDING__' in command:
            record('poll',command=command);raise SystemExit(shell(command))
        if command.startswith('test -f '):
            record('settlement_read',command=command);raise SystemExit(shell(command))
        if command.startswith('rm -f '):
            record('remote_cleanup',command=command);raise SystemExit(shell(command))
        if 'mkdir -p ~/lanes/tmp ' in command:
            record('setup');raise SystemExit(0)
        if 'mkdir ' in command:
            record('support_mkdir');raise SystemExit(0)
        record('forbidden',command=command);raise SystemExit(125)
    if name=='rsync':
        if args == ['--version']:
            record('rsync_version')
            fault=config.get('fault')
            if fault=='rsync_nonzero': raise SystemExit(23)
            if fault=='rsync_empty': raise SystemExit(0)
            if fault=='rsync_unknown': print('unqualified transfer tool');raise SystemExit(0)
            raise SystemExit(subprocess.run([config['rsync'],'--version']).returncode)
        # Use the actual installed rsync protocol and its own argument handling.
        # The remote shell is local and inert; no SSH/network/provider is used.
        remote=args[-2].split(':',1)[1]
        assert '..' not in Path(remote).parts
        if configured:
            assert remote.startswith(str(owner)+'/ext/')
            assert not any(arg.startswith('--rsync-path=') for arg in args)
            source=Path(remote)
        else:
            assert remote.startswith('./ext/')
            assert len([arg for arg in args if arg.startswith('--rsync-path=')])==1
            source=owner/remote
        record('collect',source=str(source),rsync=config['rsync'])
        result=subprocess.run([config['rsync'],'-e',str(root/'rsync-local-shell'),*args],
                              env=dict(os.environ,PATH='/usr/bin:/bin'),timeout=5)
        raise SystemExit(result.returncode)
'''

SPY = r'''
import hashlib,json,os,sys
from pathlib import Path
root=Path(os.environ['DEADLINE_FIXTURE_ROOT'])
if sys.argv[1:4]==['-I','-S','-c']:
    # The actual exclusive-output launcher runs under a real interpreter. Only
    # its later published-executor invocation reaches the inert worker below.
    os.execv(sys.executable,[sys.executable,*sys.argv[1:]])
packet=Path(os.environ['PACKET'])
row={'argv':sys.argv[1:],'cwd':str(Path.cwd()),'packet':str(packet),
     'packet_sha256':hashlib.sha256(packet.read_bytes()).hexdigest(),
     'remote_cwd':os.environ['REMOTE_CWD'],'rc_file':os.environ['RC_FILE'],
     'owner':os.environ['REMOTE_SUB_LANES'],'host_env':os.environ.get('BOUND_HOST_ENV'),
     'path':os.environ['PATH'],'physical_config':os.environ.get('REMOTE_SUB_QWEN_PHYSICAL_CONFIG'),
     'account':os.environ.get('POOL_ACCOUNT'),'lease_id':os.environ.get('POOL_LEASE_ID'),
     'layout':os.environ.get('REMOTE_SUB_LANE_ROOT_LAYOUT'),'directory':os.environ.get('LANE_DIRECTORY')}
(root/'launch-spy.json').write_text(json.dumps(row,sort_keys=True))
print('INERT PHYSICAL OWNER LAUNCH SPY: no model was executed.')
'''


class PublicationBinding(unittest.TestCase):
    def test_entire_publisher_return_is_bounded_and_exact(self):
        digest='a'*64
        valid=('/private/owner/support-releases/'+digest+'/ext\n').encode()
        self.assertEqual(helpers.published_support_root(valid,digest),'/private/owner')
        bad=[b'',valid[:-1],valid+valid,b'noise\n'+valid,valid+b'\n',
             valid.replace(b'/private/',b'private/'),valid.replace(b'/private/',b'//private/'),
             valid.replace(b'/owner/',b'/owner/../'),valid.replace(b'/owner/',b'/owner/./'),
             valid.replace(b'/owner/',b'/owner//'),valid.replace(b'ext\n',b'ext/\n'),
             valid.replace(digest.encode(),b'b'*64),valid.replace(b'owner',b'own\x00er'),
             valid.replace(b'owner',b'own\rer'),valid.replace(b'owner',b'own:er'),
             b'/' + b'x'*4096+b'\n',
             ('/support-releases/'+digest+'/ext\n').encode()]
        for raw in bad:
            with self.subTest(raw=repr(raw[:80])),self.assertRaises((ValueError,UnicodeError)):
                helpers.published_support_root(raw,digest)

    def test_rsync_dialect_refuses_unknown_or_ambiguous_whole_output(self):
        good=b'rsync  version 3.2.7  protocol version 31\n'
        bad=[b'',good[:-1],b'unknown\n',b'noise\n'+good,
             good+good,good+b'openrsync: protocol version 29\n',
             b'rsync  version injected  protocol version 31\n',
             good+b'\x00\n',good+b'x'*16384+b'\n']
        for version in bad:
            with self.subTest(version=repr(version[:80])),self.assertRaises(ValueError):
                helpers.rsync_owner_command('/private/owner',version)

    def test_shell_encoding_preserves_literal_special_characters(self):
        digest='a'*64
        owner="/private/a ' $(printf wrong) `printf wrong` space"
        raw=(owner+'/support-releases/'+digest+'/ext\n').encode()
        bound=helpers.published_support_root(raw,digest)
        result=subprocess.run(['/bin/sh','-c','printf %s '+shlex.quote(bound)],
                              capture_output=True,text=True,check=True)
        self.assertEqual(result.stdout,owner)


class QwenPhysicalConfiguration(unittest.TestCase):
    def run_config_case(self, marker):
        with tempfile.TemporaryDirectory(prefix='qwen-physical-config-') as temp:
            root=Path(temp)
            h=CredentialHarness(root)
            physical=root/'published-provider';physical.mkdir(mode=0o700)
            decoy=root/'retargeted-provider';decoy.mkdir(mode=0o700)
            (physical/'config.toml').write_text('model_provider = "owner-a"\n')
            (decoy/'config.toml').write_text('model_provider = "decoy-b"\n')
            # Same release-relative link contract verified by support_bundle.
            (root/'codex_bailian').symlink_to(physical,target_is_directory=True)
            alias=root/'provider-alias';alias.symlink_to(physical,target_is_directory=True)
            alias.unlink();alias.symlink_to(decoy,target_is_directory=True)
            # The incumbent credential fixture substitutes only the legacy host
            # path. Real selection and private config-copy bytes are unchanged.
            fake=h.fake_codex.read_text()
            needle='"codex_home": os.environ.get("CODEX_HOME"),'
            self.assertEqual(fake.count(needle),1)
            fake=fake.replace(needle,needle+'\n'
                '    "config_marker_inherited": "REMOTE_SUB_QWEN_PHYSICAL_CONFIG" in os.environ,\n'
                '    "copied_config": (Path(os.environ["CODEX_HOME"])/"config.toml").read_text(),\n'
                '    "config_mode": (Path(os.environ["CODEX_HOME"])/"config.toml").stat().st_mode & 0o777,')
            h.fake_codex.write_text(fake)
            env=h.env(LANE_LEASED='1',POOL_ACCOUNT='account-a',
                      CUSTODY_TEST_PROVIDER_HOME=str(alias))
            if marker is not None: env['REMOTE_SUB_QWEN_PHYSICAL_CONFIG']=marker
            result,_=h.run_wrapper(env=env)
            self.assertEqual(result.returncode,0,result.stderr)
            calls=h.read_jsonl(h.calls)
            self.assertEqual(len(calls),1)
            call=calls[0]
            self.assertEqual(call['credential_matches_aliases'],['account-a'])
            self.assertEqual(call['config_mode'],0o600)
            self.assertFalse(call['config_marker_inherited'])
            self.assertTrue(Path(call['codex_home']).is_relative_to(h.work))
            self.assertNotEqual(Path(call['codex_home']),physical)
            self.assertEqual((decoy/'config.toml').read_text(),'model_provider = "decoy-b"\n')
            return call['copied_config']

    def test_bound_qwen_copies_published_configuration_after_alias_retarget(self):
        self.assertEqual(self.run_config_case('1'),'model_provider = "owner-a"\n')

    def test_legacy_qwen_keeps_existing_host_configuration(self):
        for marker in (None,'0'):
            with self.subTest(marker=marker):
                self.assertEqual(self.run_config_case(marker),'model_provider = "decoy-b"\n')


class PhysicalOwnerController(unittest.TestCase):
    def setUp(self):
        with mock.patch.dict(os.environ,{'NATIVE_ROLLOUT_TEST_ROOT':str(Path.home())}):
            self.harness=harness_module.ControllerDeadline('test_plain_prelaunch_evidence_is_verified_and_ordered_before_launch')
            self.harness.setUp()
        self.addCleanup(self.harness.doCleanups)
        self.root=self.harness.root
        self.rsync=shutil.which('rsync')
        if self.rsync is None: self.skipTest('actual rsync is required for transport qualification')
        # rsync gives its remote shell a host and command arguments, just as SSH
        # does. Execute that actual server command locally without interpreting
        # the source path ourselves or replacing the rsync protocol.
        local_shell = (
            '#!'+sys.executable+'\n'
            'import os,sys\n'
            'assert sys.argv[1]=="inert-transport"\n'
            'os.execve("/bin/sh",["sh","-c"," ".join(sys.argv[2:])],'
            'dict(os.environ,PATH="/usr/bin:/bin"))\n'
        )
        harness_module.write(self.root/'rsync-local-shell',local_shell,executable=True)
        self.owner=self.root/"physical owner ' $(printf injection)"
        for relative in ('tmp','ext/lanes','support-releases','venv/bin'):
            (self.owner/relative).mkdir(parents=True,mode=0o700)
        fake_home=self.root/'remote-home';fake_home.mkdir(mode=0o700)
        (fake_home/'lanes').symlink_to(self.owner,target_is_directory=True)
        for name in ('decoy-after-publication','decoy-before-launch'):
            decoy=self.root/name
            for relative in ('tmp','ext','venv/bin'):
                (decoy/relative).mkdir(parents=True,mode=0o700)
            (decoy/'sentinel').write_text('UNTOUCHED')
            (decoy/'tmp/offline-physical_owner.txt').write_text('UNRELATED PACKET')
            (decoy/'ext/lanes_offline-physical_owner.rc').write_text('99')
            (decoy/'ext/lanes_offline-physical_owner.stdout').write_text('UNRELATED OUTPUT')
            (decoy/'ext/HOST_ENV.sh').write_text('exit 125\n')
        (self.owner/'ext/HOST_ENV.sh').write_text('export BOUND_HOST_ENV=physical\n')
        harness_module.write(self.owner/'venv/bin/python3','#!'+sys.executable+'\n'+SPY,executable=True)
        marker="if name == 'broker':\n"
        self.assertEqual(harness_module.FIXTURE.count(marker),1)
        fixture=harness_module.FIXTURE.replace(marker,PHYSICAL_FIXTURE+'\n'+marker)
        for name in ('ssh','scp','rsync','broker','ledger','claude','codex','curl','node'):
            harness_module.write(self.harness.bin/name,'#!'+sys.executable+'\n'+fixture,executable=True)
        self.addCleanup(self.restore_modes)

    def restore_modes(self):
        for path in self.owner.rglob('*'):
            if not path.is_symlink(): path.chmod(0o700 if path.is_dir() else 0o600)

    def admit_configured_owner(self):
        parent=self.root/'admitted';parent.mkdir(mode=0o700)
        destination=parent/'lanes'
        self.owner.rename(destination)
        self.owner=destination
        alias=self.root/'remote-home/lanes';alias.unlink();alias.symlink_to(self.owner,target_is_directory=True)
        for relative in ('ext/active','orch/fabric'):
            (self.owner/relative).mkdir(parents=True,mode=0o700)
        import yaml
        self.publisher_yaml_parent=str(Path(yaml.__file__).resolve().parent.parent)
        original_policy=self.root/'orch/fabric/pools.yaml'
        original_policy.write_text(json.dumps({'routing':{},'pools':{'grok':{'windows':{'weekly':{}}}}})+'\n')
        original_policy.chmod(0o600)
        policy=self.owner/'orch/fabric/pools.yaml'
        policy.write_bytes(original_policy.read_bytes());policy.chmod(0o600)
        registry=self.harness.ext/'hosts.json'
        value=json.loads(registry.read_text())
        value['fixture']['physical_lane_root']=str(self.owner)
        registry.write_text(json.dumps(value));registry.chmod(0o600)
        self.configured_owner=True

    def run_case(self,*,retarget=False,fault=None,mode='qwen',model='qwen3.8-flash',frontier_available=True):
        if not frontier_available:
            with (self.harness.ext/'slot.py').open('a') as stream:
                stream.write("\nCAPS.pop('glm-frontier', None)\n")
        (self.root/'physical-case.json').write_text(json.dumps({'retarget':retarget,'fault':fault,'owner':str(self.owner),'rsync':self.rsync,
            'configured':getattr(self,'configured_owner',False),
            'yaml_parent':getattr(self,'publisher_yaml_parent',None)}))
        witness=('Offline regression requires the requested GLM acquisition tuple; all carriers and the worker are inert.'
                 if mode=='glm' else None)
        return self.harness.run_controller('physical_owner',budget=18,mode=mode,model=model,
                                           escalation_reason=witness)

    def assert_bound_launch(self,result,*,mode='qwen',model='qwen3.8-flash',acquisition_pool='bailian'):
        diagnostic=result['stderr']
        output=self.owner/'ext/lanes_offline-physical_owner.stdout'
        if output.exists(): diagnostic+='\nINERT REMOTE OUTPUT: '+output.read_text()[:2000]
        self.assertEqual(result['returncode'],0,diagnostic)
        spy=json.loads((self.root/'launch-spy.json').read_text())
        self.assertEqual(spy['cwd'],str(self.owner/'ext'))
        self.assertEqual(spy['packet'],str(self.owner/'tmp/offline-physical_owner.txt'))
        self.assertEqual(spy['owner'],str(self.owner))
        self.assertEqual(spy['physical_config'],'1' if mode=='qwen' else '0')
        self.assertEqual(spy['remote_cwd'],'~')
        self.assertEqual(spy['host_env'],'physical')
        self.assertEqual(spy['rc_file'],str(self.owner/'ext/lanes_offline-physical_owner.rc'))
        self.assertEqual(spy['path'].split(':')[0],str(self.owner/'venv/bin'))
        self.assertTrue(Path(spy['argv'][0]).is_relative_to(self.owner/'support-releases'))
        self.assertEqual(Path(spy['argv'][0]).name,'remote_sub_exec.py')
        self.assertEqual(spy['argv'][1:4],['offline-physical_owner',mode,spy['packet']])
        self.assertEqual(spy['argv'][-1],model)
        self.assertEqual(spy['account'],'fixture-account')
        self.assertEqual(spy['lease_id'],'0123456789ab')
        acquired=[row for row in result['events'] if row['stage']=='acquire']
        self.assertEqual(len(acquired),1)
        self.assertEqual(acquired[0]['acquisition_pool'],acquisition_pool)
        self.assertEqual(acquired[0]['requested_model'],model)
        self.assertEqual(acquired[0]['task_class'],'remote-'+mode)
        ledger=[row for row in result['events'] if row['stage']=='ledger']
        self.assertEqual(len(ledger),1)
        self.assertEqual(ledger[0]['pool'],'glm' if mode=='glm' else 'bailian')
        self.assertEqual(spy['packet_sha256'],hashlib.sha256(self.harness.packet.read_bytes()).hexdigest())
        stages=[row['stage'] for row in result['events']]
        self.assertEqual(stages.count('launch'),1)
        self.assertLess(stages.index('transport_read'),stages.index('launch'))
        if mode=='glm':
            self.assertEqual(stages.count('account_ready'),1)
            self.assertLess(stages.index('account_ready'),stages.index('launch'))
        self.assertIn('poll',stages);self.assertIn('collect',stages);self.assertIn('remote_cleanup',stages)
        self.assertFalse((self.owner/'tmp/offline-physical_owner.txt').exists())
        for name in ('decoy-after-publication','decoy-before-launch'):
            self.assertEqual((self.root/name/'sentinel').read_text(),'UNTOUCHED')
            self.assertEqual((self.root/name/'tmp/offline-physical_owner.txt').read_text(),'UNRELATED PACKET')
            self.assertEqual((self.root/name/'ext/lanes_offline-physical_owner.rc').read_text(),'99')
            self.assertEqual((self.root/name/'ext/lanes_offline-physical_owner.stdout').read_text(),'UNRELATED OUTPUT')
        tracked,_=self.harness.tracked_log_events('offline-physical_owner')
        self.assertEqual([name for name,_ in tracked],['RUN_RESERVED','LEASE_OK','SUPPORT_VERSION_READY',
            'TRANSPORT_VERIFIED','LAUNCH_BINDING','LAUNCH','LAUNCH_ATTEMPT'])
        receipt=json.loads((self.harness.ext/'state/remote_sub/offline-physical_owner.transport-verified.json').read_text())
        self.assertEqual(receipt['schema'],'mastermind.transport_verification.v3')
        self.assertEqual(receipt['packet_sha256'],spy['packet_sha256'])
        self.assertEqual(receipt['acquisition_pool'],acquisition_pool)
        self.assertEqual([event for name,event in tracked if name=='LEASE_OK'],
                         ['LEASE_OK pool='+acquisition_pool])
        binding=json.loads(next(event.split(' ',1)[1] for name,event in tracked if name=='LAUNCH_BINDING'))
        self.assertEqual(binding['schema'],'mastermind.fabric_plain_launch_binding.v3')
        self.assertEqual(binding['pool'],'glm' if mode=='glm' else 'bailian')
        self.assertEqual(binding['acquisition_pool'],acquisition_pool)
        self.assertEqual(binding['transport']['acquisition_pool'],acquisition_pool)
        self.assertEqual((binding['lease_id'],binding['account']),(spy['lease_id'],spy['account']))
        self.assertEqual(spy['directory'],str(self.owner))
        if getattr(self,'configured_owner',False):
            self.assertEqual(receipt['lane_root'],binding['transport']['lane_root'])
            self.assertEqual(receipt['lane_root']['binding']['path'],str(self.owner))
            self.assertIn('exclusive_packet',stages)
            self.assertIn('root_layout_read',stages)
            self.assertNotIn('rsync_version',stages)
            self.assertEqual(len(receipt['files']),38)
        else:
            self.assertIsNone(receipt['lane_root'])
            self.assertIsNone(binding['transport']['lane_root'])
            self.assertEqual(len(receipt['files']),37)


    def test_configured_frontier_uses_admitted_layout_through_actual_controller(self):
        self.admit_configured_owner()
        self.assert_bound_launch(self.run_case(mode='glm',model='glm-5.3'),
            mode='glm',model='glm-5.3',acquisition_pool='glm-frontier')

    def test_configured_qwen_keeps_frozen_owner_after_alias_retarget(self):
        self.admit_configured_owner()
        self.assert_bound_launch(self.run_case(retarget=True))
        self.assertEqual((self.root/'remote-home/lanes').resolve(),self.root/'decoy-before-launch')

    def test_configured_publisher_disagreement_cannot_select_fallback(self):
        self.admit_configured_owner()
        result=self.run_case(fault='publisher_other_owner')
        self.assertEqual(result['returncode'],78,result['stderr'])
        self.assertIn('SUPPORT_OWNER_REGISTRY_MISMATCH',result['stderr'])
        stages=[row['stage'] for row in result['events']]
        self.assertIn('root_layout_read',stages)
        self.assertIn('support_publish',stages)
        self.assertNotIn('transport_read',stages)
        self.assertNotIn('rsync_version',stages)
        self.assertNotIn('launch',stages)
        self.assertFalse((self.root/'launch-spy.json').exists())

    def test_configured_unsafe_layout_refuses_without_publisher_fallback(self):
        self.admit_configured_owner()
        (self.owner/'ext').chmod(0o777)
        result=self.run_case()
        self.assertEqual(result['returncode'],78,result['stderr'])
        self.assertIn('REMOTE_LANE_ROOT_UNQUALIFIED',result['stderr'])
        stages=[row['stage'] for row in result['events']]
        self.assertIn('root_layout_read',stages)
        self.assertNotIn('support_publish',stages)
        self.assertNotIn('rsync_version',stages)
        self.assertNotIn('launch',stages)
        self.assertFalse((self.root/'launch-spy.json').exists())

    def test_unknown_empty_or_failed_rsync_version_refuses_before_readback(self):
        for fault in ('rsync_unknown','rsync_empty','rsync_nonzero'):
            with self.subTest(fault=fault):
                # Each case owns an independent original run and directory.
                case=PhysicalOwnerController('test_physical_binding_runs_real_reader_and_inert_shell')
                case.setUp()
                try:
                    result=case.run_case(fault=fault)
                    self.assertNotEqual(result['returncode'],0)
                    stages=[row['stage'] for row in result['events']]
                    self.assertNotIn('launch',stages)
                    self.assertNotIn('transport_read',stages)
                    self.assertIn('RSYNC_DIALECT_',result['stderr'])
                finally:
                    case.doCleanups()

    def test_flat_owner_preserves_direct_path_behavior(self):
        alias=self.root/'remote-home/lanes'
        alias.unlink()
        self.owner.rename(alias)
        self.owner=alias
        self.assert_bound_launch(self.run_case())

    def test_glm_frontier_acquisition_reaches_bound_launch(self):
        result=self.run_case(mode='glm',model='glm-5.3')
        self.assert_bound_launch(result,mode='glm',model='glm-5.3',acquisition_pool='glm-frontier')

    def test_glm_without_frontier_capability_keeps_ordinary_pool(self):
        result=self.run_case(mode='glm',model='glm-5.3',frontier_available=False)
        self.assert_bound_launch(result,mode='glm',model='glm-5.3',acquisition_pool='glm')

    def test_glm_flash_keeps_ordinary_acquisition_pool(self):
        result=self.run_case(mode='glm',model='glm-5.3-flash')
        self.assert_bound_launch(result,mode='glm',model='glm-5.3-flash',acquisition_pool='glm')

    def test_physical_binding_runs_real_reader_and_inert_shell(self):
        self.assert_bound_launch(self.run_case())

    def test_alias_retarget_after_publication_and_before_launch_never_changes_owner(self):
        self.assert_bound_launch(self.run_case(retarget=True))
        self.assertEqual((self.root/'remote-home/lanes').resolve(),self.root/'decoy-before-launch')

    def test_missing_or_unsafe_physical_evidence_refuses_before_launch(self):
        result=self.run_case(fault='packet_symlink')
        self.assertNotEqual(result['returncode'],0)
        self.assertIn('TRANSPORT_READBACK_REFUSED',result['stderr'])
        self.assertNotIn('launch',[row['stage'] for row in result['events']])
        self.assertFalse((self.root/'launch-spy.json').exists())

    def test_unsafe_physical_parent_refuses_before_launch(self):
        result=self.run_case(fault='unsafe_parent')
        self.assertNotEqual(result['returncode'],0)
        self.assertIn('TRANSPORT_READBACK_REFUSED',result['stderr'])
        self.assertNotIn('launch',[row['stage'] for row in result['events']])

    def test_changed_physical_code_refuses_before_launch(self):
        result=self.run_case(fault='changed_code')
        self.assertNotEqual(result['returncode'],0)
        self.assertIn('transport_observation_code_mismatch',result['stderr'])
        self.assertNotIn('launch',[row['stage'] for row in result['events']])

    def test_duplicate_publication_return_refuses_before_readback(self):
        result=self.run_case(fault='duplicate_return')
        self.assertEqual(result['returncode'],78,result['stderr'])
        self.assertIn('SUPPORT_OWNER_BINDING_REFUSED',result['stderr'])
        stages=[row['stage'] for row in result['events']]
        self.assertNotIn('transport_read',stages);self.assertNotIn('launch',stages)


if __name__=='__main__':
    unittest.main()

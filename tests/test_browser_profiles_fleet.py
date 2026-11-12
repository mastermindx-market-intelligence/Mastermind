"""Focused lifecycle, identity, SSH dispatch and destination-file boundary tests."""
from __future__ import annotations
import copy
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from integrations.chairman_surfaces import _web_sol_native_host_impl as native
from integrations.hermes_harness import browser_bridge as bridge,browser_routes as routes
from integrations.hermes_harness.install_browser import write_owned,digest,install_profiles,json_bytes

ROOT=Path(__file__).resolve().parents[1]


class NativeLifecycle(unittest.TestCase):
    def test_cold_root_live_owner_and_qualified_crash_recovery(self):
        with tempfile.TemporaryDirectory(prefix="mb-") as directory:
            endpoint=Path(directory)/"private/a.sock"
            code=("from pathlib import Path;import os,sys;"
                "from integrations.chairman_surfaces import _web_sol_native_host_impl as n;"
                "s=n.open_private_server(Path(sys.argv[1]),owner_uid=os.getuid());"
                "print('READY',flush=True);sys.stdin.read()")
            owner=subprocess.Popen([sys.executable,"-c",code,str(endpoint)],cwd=ROOT,stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)
            try:
                self.assertEqual(owner.stdout.readline().strip(),"READY")
                lock=Path(str(endpoint)+".lock");inode=lock.stat().st_ino;socket_inode=endpoint.stat().st_ino
                self.assertEqual(endpoint.parent.stat().st_mode&0o777,0o700)
                with self.assertRaisesRegex(native.NativeHostError,"socket_owner_live"):
                    native.open_private_server(endpoint,owner_uid=os.getuid())
                self.assertEqual(endpoint.stat().st_ino,socket_inode)
                owner.terminate();owner.wait(timeout=3)
                replacement=native.open_private_server(endpoint,owner_uid=os.getuid())
                self.assertEqual(lock.stat().st_ino,inode)
                with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as client:client.connect(str(endpoint))
                native.close_private_server(replacement,endpoint,owner_uid=os.getuid());self.assertFalse(endpoint.exists())
            finally:
                if owner.poll() is None:owner.kill();owner.wait()
                owner.stdin.close();owner.stdout.close()

    def test_legacy_unsafe_and_symlink_paths_are_preserved(self):
        with tempfile.TemporaryDirectory(prefix="mb-") as directory:
            root=Path(directory);endpoint=root/"legacy.sock"
            old=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);old.bind(str(endpoint));endpoint.chmod(0o600);old.close()
            inode=endpoint.stat().st_ino
            with self.assertRaisesRegex(native.NativeHostError,"legacy_owner_unreconciled"):
                native.open_private_server(endpoint,owner_uid=os.getuid())
            self.assertEqual(endpoint.stat().st_ino,inode)
            root.chmod(0o755)
            with self.assertRaisesRegex(native.NativeHostError,"parent_unsafe"):
                native.open_private_server(root/"other.sock",owner_uid=os.getuid())
            root.chmod(0o700);link=root/"link.sock";link.symlink_to(endpoint)
            with self.assertRaisesRegex(native.NativeHostError,"path_unsafe"):
                native.open_private_server(link,owner_uid=os.getuid())
            self.assertTrue(link.is_symlink())


class Profiles(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory(prefix="mb-");self.addCleanup(self.temporary.cleanup)
        self.root=Path(self.temporary.name);self.extension=self.root/"extension";self.extension.mkdir()
        self.data=self.root/"Chrome";self.profile=self.data/"Profile 12";self.profile.mkdir(parents=True)
        self.uploads=self.root/"uploads";self.uploads.mkdir();self.file=self.uploads/"fixture.txt";self.file.write_text("fixture")
        self.id="a"*64
        write_owned(self.extension/"instance_config.js",('globalThis.MMX_WEB_SOL_INSTANCE = Object.freeze('+json.dumps({"instanceId":self.id})+');\n').encode())
        write_owned(self.extension/"manifest.json",b'{"version":"0.4.1"}')
        write_owned(self.profile/"Secure Preferences",json_bytes({"extensions":{"settings":{routes.EXTENSION_ID:{"path":str(self.extension),"disable_reasons":[]}}}}))
        self.row=dict(host_ref="m2",browser_id=self.id,alias="mastermindx",label="M2 · MastermindX",manager="chrome",
            profile_directory="Profile 12",profile_name="Chris",account_hint="mastermindx6031@gmail.com",data_directory=str(self.data),
            extension_path=str(self.extension),native_host_manifest=str(self.root/"host.json"),chrome_executable=sys.executable,upload_roots=[str(self.uploads)])
        self.document=dict(schema=routes.SCHEMA,local_host_ref="m2",hosts=[dict(host_ref="m2",label="M2 Studio",transport="local")],profiles=[self.row])
        self.inventory=self.root/"deployments.json";self.save()

    def save(self):
        self.inventory.write_text(json.dumps(self.document));self.inventory.chmod(0o600)
    def run_action(self,args,exchange=None,**kw):
        return bridge.execute(args,native_session_id="test-session",profile_ref="m2:/profile",bindings_path=self.inventory,
            exchange=exchange or (lambda *a,**k:{"status":"OK","data":{"connection_id":"connection-one"}}),**kw)

    def test_named_inventory_keeps_closed_and_uninstalled_profiles(self):
        result=self.run_action({"action":"browsers"})["browsers"][0]
        self.assertEqual(result["profile_directory"],"Profile 12");self.assertTrue(result["installed"])
        self.assertEqual(result["connectivity"],"NOT_CHECKED")
        (self.profile/"Secure Preferences").write_text("{}")
        result=self.run_action({"action":"browsers"})["browsers"][0]
        self.assertFalse(result["installed"]);self.assertEqual(result["activation"],"CHROME_LOAD_REQUIRED")

    def test_same_browser_id_on_two_hosts_requires_explicit_host(self):
        remote=dict(host_ref="mini1",label="Mini1",transport="ssh",ssh_alias="mmx-mini1",python_executable="/usr/bin/python3",
            source_root="/owned/release",bindings_path="/owned/inventory.json",manifest_sha256="b"*64)
        self.document["hosts"].append(remote);self.document["profiles"].append(dict(self.row,host_ref="mini1"));self.save()
        result=self.run_action({"action":"status","browser_id":self.id})
        self.assertEqual(result["reason"],"BROWSER_HOST_REQUIRED")
        self.assertEqual(self.run_action({"action":"status","browser_id":self.id,"host_ref":"m2"})["routing"]["host_ref"],"m2")
        with patch.object(routes,"remote_call",return_value={"state":"OBSERVED","proof":"remote"}) as remote_call:
            result=self.run_action({"action":"status","browser_id":self.id,"host_ref":"mini1"})
            self.assertEqual(result["proof"],"remote");self.assertEqual(remote_call.call_count,1)
            self.assertEqual(remote_call.call_args.args[0]["ssh_alias"],"mmx-mini1")
            self.assertEqual(self.run_action({"action":"status","browser_id":self.id,"host_ref":"mini1"},local_only=True)["reason"],"REMOTE_FORWARDING_DISABLED")

    def test_destination_upload_uses_canonical_path_and_rejects_caller_root(self):
        alias=self.root/"file-alias";alias.symlink_to(self.file);seen=[]
        args=dict(action="upload",host_ref="m2",browser_id=self.id,connection_id="connection-one",tab_id=1,
            url_fingerprint="b"*64,snapshot_id="snapshot-observation-one",options={"ref":"node-one","files":[str(alias)]})
        result=self.run_action(args,exchange=lambda *a,**k:(seen.append(k) or {"status":"OK"}))
        self.assertEqual(result["state"],"RECEIPT");self.assertEqual(seen[0]["params"]["files"],[str(self.file.resolve())])
        self.assertEqual(args["options"]["files"],[str(alias)])
        outside=self.root/"caller-file";outside.write_text("caller-only")
        args["options"]["files"]=[str(outside)]
        with patch.dict(os.environ,{"MMX_BROWSER_UPLOAD_ROOTS":json.dumps([str(self.root)])}):
            self.assertEqual(self.run_action(args,local_only=True)["reason"],"UPLOAD_FILE_OUTSIDE_ROOTS")
        args["options"]=[];self.assertEqual(self.run_action(args)["reason"],"INVALID_ARGUMENTS")

    def test_launch_only_selected_absent_endpoint_and_no_status_side_effect(self):
        from integrations.chairman_surfaces.web_sol_client import WebSolExtensionError
        def unavailable(*a,**k):raise WebSolExtensionError("extension_unavailable")
        with patch.object(routes.subprocess,"Popen") as popen,patch.object(routes.sys,"platform","darwin"),patch.object(bridge.os.path,"lexists",return_value=False):
            popen.return_value.pid=123
            self.run_action({"action":"browsers","options":{"probe":True}},exchange=unavailable);popen.assert_not_called()
            result=self.run_action({"action":"launch","host_ref":"m2","browser_id":self.id},exchange=unavailable)
            self.assertEqual(result["connectivity"],"LAUNCH_REQUESTED");self.assertFalse(result["launch_verified"])
            self.assertIn("--profile-directory=Profile 12",popen.call_args.args[0]);self.assertIn("--user-data-dir="+str(self.data),popen.call_args.args[0])
            self.assertEqual(popen.call_count,1)
        with patch.object(bridge.os.path,"lexists",return_value=True),patch.object(routes,"launch") as launch:
            self.assertEqual(self.run_action({"action":"launch","browser_id":self.id},exchange=unavailable)["reason"],"PROFILE_CONNECTION_UNRECONCILED")
            launch.assert_not_called()

    def test_wrong_configured_extension_is_not_selected(self):
        (self.extension/"instance_config.js").write_text('Object.freeze({"instanceId":"'+"c"*64+'"});')
        result=self.run_action({"action":"status","browser_id":self.id})
        self.assertEqual(result["reason"],"PROFILE_IDENTITY_MISMATCH")

    def test_installer_cas_preserves_newer_writer_and_backup(self):
        path=self.root/"installed";write_owned(path,b"old");old=digest(path.read_bytes());path.write_bytes(b"writer")
        with self.assertRaisesRegex(RuntimeError,"no overwrite"):write_owned(path,b"new",expected=old)
        self.assertEqual(path.read_bytes(),b"writer")
        write_owned(path,b"new",expected=digest(b"writer"));self.assertEqual(path.read_bytes(),b"new")
        self.assertEqual(path.with_name(path.name+".previous."+digest(b"writer")[:16]).read_bytes(),b"writer")


class PreparedUpgrade(unittest.TestCase):
    def fixture(self,root):
        from integrations.chairman_surfaces.web_sol_deployment import _CENSUS_SOURCE_NAMES
        base=root/"install";chrome=root/"Chrome";(chrome/"Default").mkdir(parents=True)
        uploads=root/"uploads";uploads.mkdir()
        enrollment=dict(host_ref="m2",label="M2",remote_hosts=[],remote_profiles=[],profiles=[dict(
            alias="mastermindx",label="M2 · MastermindX",profile_directory="Default",profile_name="MastermindX",
            account_hint="mastermindx6031@gmail.com",data_directory=str(chrome),chrome_executable=sys.executable,
            upload_roots=[str(uploads)])])
        releases=[]
        for generation in ("1","2"):
            release=base/"releases"/(generation*40);files={}
            for name in sorted(_CENSUS_SOURCE_NAMES):
                relative="integrations/chairman_surfaces/web_sol_extension/"+name
                content=(ROOT/relative).read_bytes()
                if generation=="2" and name=="census.css":content+=b"\n/* installer upgrade fixture */\n"
                write_owned(release/relative,content);files[relative]=digest(content)
            manifest=dict(schema="mastermind.browser_direct_build.v1",source_commit=generation*40,files=files)
            write_owned(release/"BUILD.json",json_bytes(manifest));releases.append((release,manifest))
        return base,chrome,enrollment,releases

    def test_known_prepared_assets_upgrade_an_unloaded_staging_root_in_place(self):
        # The staging folder is not loaded by any Chrome, so re-installing into
        # the same staging root updates the prepared assets in place (CAS with
        # a .previous backup) — an unrelated enrolled row survives, and a rerun
        # is a byte-identical no-op.
        with tempfile.TemporaryDirectory(prefix="mb-") as directory:
            root=Path(directory);base,chrome,enrollment,releases=self.fixture(root)
            staging=root/"staging"
            with patch.object(Path,"home",return_value=root):
                inventory,receipts=install_profiles(*releases[0],base,Path(sys.executable),enrollment,staging_root=staging)
                prepared=Path(receipts[0]["extension_path"]);asset=prepared/"census.css";old=asset.read_bytes()
                # An unrelated enrolled row must survive the update.
                document=json.loads(inventory.read_bytes());other=dict(document["profiles"][0],browser_id="a"*64,alias="unrelated")
                document["profiles"].append(other);write_owned(inventory,json_bytes(document),expected=digest(inventory.read_bytes()))
                _,updated=install_profiles(*releases[1],base,Path(sys.executable),enrollment,prior_source="1"*40,staging_root=staging)
                self.assertNotEqual(asset.read_bytes(),old)
                self.assertEqual(asset.with_name(asset.name+".previous."+digest(old)[:16]).read_bytes(),old)
                self.assertEqual(updated[0]["activation"],"CHROME_LOAD_REQUIRED")
                self.assertIn(other,json.loads(inventory.read_bytes())["profiles"])
                before=inventory.read_bytes()
                install_profiles(*releases[1],base,Path(sys.executable),enrollment,prior_source="1"*40,staging_root=staging)
                self.assertEqual(inventory.read_bytes(),before)

    def test_staging_root_a_chrome_has_loaded_refuses_the_prepared_rewrite(self):
        # BR-COMPATFIX (MED-1): once Chrome has loaded from the staged folder,
        # re-installing into the same staging root is refused by name instead
        # of rewriting loaded bytes under a running service worker. The move
        # to new bytes is the operator's reload from a fresh staging root.
        with tempfile.TemporaryDirectory(prefix="mb-") as directory:
            root=Path(directory);base,chrome,enrollment,releases=self.fixture(root)
            staging=root/"staging"
            with patch.object(Path,"home",return_value=root):
                inventory,receipts=install_profiles(*releases[0],base,Path(sys.executable),enrollment,staging_root=staging)
                prepared=Path(receipts[0]["extension_path"])
                write_owned(chrome/"Default/Secure Preferences",json_bytes({"extensions":{"settings":{
                    routes.EXTENSION_ID:{"path":str(prepared),"disable_reasons":[]}}}}))
                asset=prepared/"census.css";old=asset.read_bytes()
                inventory_before=inventory.read_bytes()
                with self.assertRaises(RuntimeError) as caught:
                    install_profiles(*releases[1],base,Path(sys.executable),enrollment,prior_source="1"*40,staging_root=staging)
                self.assertIn(str(prepared),str(caught.exception))
                self.assertEqual(asset.read_bytes(),old)
                self.assertEqual(inventory.read_bytes(),inventory_before)
                self.assertFalse((releases[1][0]/"chrome").exists())
                # The upgrade path is a fresh per-release staging root: the
                # loaded folder keeps its bytes and the receipt asks for a reload.
                fresh=root/"staging-next"
                _,updated=install_profiles(*releases[1],base,Path(sys.executable),enrollment,prior_source="1"*40,staging_root=fresh)
                self.assertEqual(asset.read_bytes(),old)
                self.assertEqual(updated[0]["activation"],"CHROME_RELOAD_REQUIRED")
                self.assertEqual(Path(updated[0]["extension_path"]),fresh/"Chrome-mastermindx")

    def test_edited_source_or_generated_identity_refuses_before_writes(self):
        for name in ("census.css","instance_config.js"):
            with self.subTest(name=name),tempfile.TemporaryDirectory(prefix="mb-") as directory:
                root=Path(directory);base,chrome,enrollment,releases=self.fixture(root)
                staging=root/"staging"
                with patch.object(Path,"home",return_value=root):
                    inventory,receipts=install_profiles(*releases[0],base,Path(sys.executable),enrollment,staging_root=staging)
                    prepared=Path(receipts[0]["extension_path"]);asset=prepared/name;asset.write_bytes(b"local writer")
                    native_path=Path(receipts[0]["native_host_manifest"])
                    before=(inventory.read_bytes(),native_path.read_bytes())
                    with self.assertRaisesRegex(RuntimeError,"prepared extension changed"):
                        install_profiles(*releases[1],base,Path(sys.executable),enrollment,prior_source="1"*40,staging_root=staging)
                    self.assertEqual(asset.read_bytes(),b"local writer")
                    self.assertEqual((inventory.read_bytes(),native_path.read_bytes()),before)
                    self.assertFalse((releases[1][0]/"chrome").exists())


class SSHDispatch(unittest.TestCase):
    def setUp(self):
        self.host=dict(host_ref="mini1",ssh_alias="mmx-mini1",python_executable="/usr/bin/python3",source_root="/release",manifest_sha256="b"*64,bindings_path="/inventory")
        self.envelope=dict(session_id="test",operation_key="hermes-browser-"+"1"*32,nonce="2"*48,arguments={"action":"open"})
        self.real_popen=subprocess.Popen
    def invoke(self,program,**kwargs):
        observed=[]
        def fake(argv,**options):
            observed.append(argv)
            return self.real_popen([sys.executable,"-u","-c",program],**options)
        with patch.object(routes.subprocess,"Popen",side_effect=fake):
            try:return routes.remote_call(self.host,self.envelope,"m2:/profile",**kwargs),observed
            finally:self.assertEqual(len(observed),1)
    def test_verified_readiness_then_one_dispatch_and_no_forwarding(self):
        program='import json,sys;print(json.dumps({"state":"REMOTE_READY","host_ref":"mini1"}),flush=True);r=json.loads(sys.stdin.readline());print(json.dumps({"state":"OBSERVED","nonce":r["nonce"]}))'
        result,argv=self.invoke(program);self.assertEqual(result["nonce"],self.envelope["nonce"])
        for flag in ("-oStrictHostKeyChecking=yes","-oForwardAgent=no","-oClearAllForwardings=yes","-oControlPath=none"):
            self.assertIn(flag,argv[0])
    def test_preflight_rejection_and_postdispatch_loss_are_distinct(self):
        with self.assertRaises(routes.RouteError) as caught:
            self.invoke('import sys;sys.stderr.write("Host key verification failed");sys.exit(255)')
        self.assertEqual(caught.exception.code,"REMOTE_HOST_KEY_REJECTED");self.assertFalse(caught.exception.possible)
        with self.assertRaises(routes.RouteError) as caught:
            self.invoke('import json,sys;print(json.dumps({"state":"REMOTE_READY","host_ref":"mini1"}),flush=True);sys.stdin.readline();sys.exit(1)')
        self.assertTrue(caught.exception.possible)
    def test_identity_and_budget_are_checked_before_action(self):
        with self.assertRaisesRegex(routes.RouteError,"IDENTITY_MISMATCH"):
            self.invoke('print(\'{"state":"REMOTE_READY","host_ref":"wrong"}\',flush=True);input()')
        with self.assertRaises(routes.RouteError) as caught:
            self.invoke('print(\'{"state":"REMOTE_READY","host_ref":"mini1"}\',flush=True);input()',timeout=1)
        self.assertEqual(caught.exception.code,"REMOTE_BUDGET_EXHAUSTED");self.assertFalse(caught.exception.possible)


if __name__=="__main__":unittest.main(verbosity=2)

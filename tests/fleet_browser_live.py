"""M2 native Hermes -> strict SSH -> remote helper/native host -> real Chrome."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import select
import shlex
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]


def main(args):
    command=[args.remote_python,"-B",str(Path(args.remote_root)/"tests/fleet_fixture_host.py"),"--source-commit",args.source_commit,
        "--host-ref",args.host_ref,"--ssh-alias",args.ssh_alias,"--chrome",args.remote_chrome]
    # PYTHONPATH is a fixed test source path, not an agent-provided command.
    remote="cd "+shlex.quote(args.remote_root)+" && PYTHONPATH="+shlex.quote(args.remote_root)+" "+shlex.join(command)
    argv=["/usr/bin/ssh","-T","-oBatchMode=yes","-oStrictHostKeyChecking=yes","-oUpdateHostKeys=no","-oForwardAgent=no",
        "-oClearAllForwardings=yes","-oControlMaster=no","-oControlPath=none","-oConnectionAttempts=1","-oConnectTimeout=5",args.ssh_alias,remote]
    fixture=subprocess.Popen(argv,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,bufsize=0)
    try:
        ready=bytearray()
        while b"\n" not in ready:
            if not select.select([fixture.stdout],[],[],45)[0]:raise RuntimeError("remote fixture readiness timeout")
            chunk=os.read(fixture.stdout.fileno(),1)
            if not chunk:raise RuntimeError("remote fixture exited: "+fixture.stderr.read(10000).decode())
            ready.extend(chunk)
        ready=json.loads(ready);assert ready["state"]=="FIXTURE_READY",ready
        with tempfile.TemporaryDirectory(prefix="mmx-fleet-consumer-") as directory:
            stage=Path(directory);profile=stage/"hermes";profile.mkdir()
            inventory=stage/"inventory.json";inventory.write_text(json.dumps(dict(schema="mastermind.browser_deployments.v2",local_host_ref="m2",
                hosts=[dict(host_ref="m2",label="M2",transport="local"),ready["host"]],profiles=[ready["profile"]])))
            probe=[args.hermes_python,str(ROOT/"tests/hermes_native_browser_live.py"),"--probe","--profile",str(profile),
                "--instance",ready["profile"]["browser_id"],"--inventory",str(inventory),"--fixture-url",ready["fixture_url"],
                "--source-commit",args.source_commit,"--hermes-runtime",args.hermes_runtime,"--host-ref",args.host_ref,
                "--browser-upload",ready["browser_upload"],"--upload-denied",ready["upload_denied"]]
            if args.skip_upload:probe.append("--skip-upload")
            result=subprocess.run(probe,cwd=ROOT,env=dict(os.environ,PYTHONPATH=str(ROOT)),capture_output=True,text=True,timeout=300)
            if result.returncode:raise RuntimeError(result.stdout+result.stderr[-10000:])
            proof=json.loads(result.stdout);assert proof["state"]=="PASS" and proof["remote_ssh"],proof
            evidence=ROOT/"evidence";evidence.mkdir(exist_ok=True)
            (evidence/"fleet-browser-live.json").write_text(json.dumps(proof,indent=2)+"\n")
            print(json.dumps(proof),flush=True)
    finally:
        try:
            output,error=fixture.communicate(b"close\n",timeout=25)
            if fixture.returncode:print("fixture cleanup: "+error.decode()[-1500:],file=sys.stderr)
        except subprocess.TimeoutExpired:
            fixture.kill();fixture.wait();raise RuntimeError("remote fixture cleanup unconfirmed; its ten-minute lease remains")


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--skip-upload",action="store_true")
    for name in ("remote-python","remote-root","remote-chrome","ssh-alias","host-ref","source-commit","hermes-runtime","hermes-python"):
        parser.add_argument("--"+name,required=True)
    main(parser.parse_args())

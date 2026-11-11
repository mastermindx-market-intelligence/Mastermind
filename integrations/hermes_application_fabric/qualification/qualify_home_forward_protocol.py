"""Finite three-namespace Chisel proof for the existing home-forward contract.

Runs only disposable, labelled, internal-network Docker fixtures with the
already installed qualified binary. No host ports, production credentials,
service units or production tunnel operations are read or changed.
"""
from __future__ import annotations
import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import stat
import subprocess
import time

NODE = r'''
import json,os,socketserver,subprocess,sys,threading,time
from pathlib import Path
mode=sys.argv[1];root=Path("/fixture");values=json.loads((root/"fixture-credentials.json").read_text())
binary="/fixture/chisel"
if mode=="server":
 subprocess.run([binary,"server","--host","127.0.0.1","--port","0","--keygen","/tmp/server.key"],
                env={},capture_output=True,check=True,timeout=5)
 os.execv(binary,[binary,"server","--host","0.0.0.0","--port","8099","--reverse",
                   "--authfile","/fixture/users.json","--keyfile","/tmp/server.key","--keepalive","20s"])
class Handler(socketserver.BaseRequestHandler):
 def handle(self):
  self.request.settimeout(1)
  try:
   data=b""
   while b"\n" not in data and len(data)<160:
    part=self.request.recv(160-len(data))
    if not part:return
    data+=part
   if not data.endswith(b"\n"):return
   token=data.decode("ascii").strip()
   print("ARRIVAL "+token,flush=True)
   self.request.sendall((("APP:" if mode=="app" else "SSH:")+token+"\n").encode())
  except (OSError,UnicodeError):return
server=socketserver.ThreadingTCPServer(("127.0.0.1",4142 if mode=="app" else 22220),Handler)
threading.Thread(target=server.serve_forever,daemon=True).start()
fp=sys.argv[2]
remotes=(["R:127.0.0."+str(i)+":50142:127.0.0.1:4142" for i in (1,2,3)] if mode=="app" else
 ["R:127.0.0.1:2222:127.0.0.1:22220","127.0.0.2:50142:127.0.0.2:50142","127.0.0.3:50142:127.0.0.3:50142"])
child=subprocess.Popen([binary,"client","--fingerprint",fp,"--keepalive","20s","http://vps:8099",*remotes],
                       env={"AUTH":values[mode]},stdin=subprocess.DEVNULL)
raise SystemExit(child.wait())
'''
PROBE = r'''import socket,sys,json
try:
 with socket.create_connection((sys.argv[1],int(sys.argv[2])),timeout=1) as s:
  s.settimeout(1);s.sendall((sys.argv[3]+"\n").encode());data=b""
  while not data.endswith(b"\n"):
   piece=s.recv(256)
   if not piece:break
   data+=piece
  print(json.dumps({"reply":data.decode("ascii")}))
except (OSError,UnicodeError):print(json.dumps({"reply":None}))
'''


def require(value, message):
    if not value:
        raise RuntimeError(message)


def execute(binary, expected_sha256, image, root):
    binary, root = Path(binary), Path(root)
    require(os.geteuid() != 0, "fixture must run without root")
    require(root.is_absolute() and root.parent == Path("/tmp")
            and root.name.startswith("mmx-hermes-home-protocol-"), "fixture path refused")
    info = binary.lstat()
    require(stat.S_ISREG(info.st_mode) and info.st_uid == 0 and not info.st_mode & 0o022
            and hashlib.sha256(binary.read_bytes()).hexdigest() == expected_sha256,
            "qualified binary custody differs")
    require(re.fullmatch(r"sha256:[0-9a-f]{64}", image), "exact fixture image required")
    require(subprocess.run([str(binary), "--version"], capture_output=True, text=True,
                           check=True, timeout=5).stdout.strip() == "1.12.0", "binary version differs")
    root.mkdir(mode=0o700, exist_ok=False)
    operation = "h4-home-proof-" + secrets.token_hex(8)
    network = operation + "-net"
    names = {mode: operation + "-" + mode for mode in ("server", "app", "home")}
    label = "mastermind.hermes-home-proof=" + operation
    events = []
    receipt = {"schema": "hermes_application_home_protocol_fixture_v1",
               "operation": operation, "binary_sha256": expected_sha256, "version": "1.12.0",
               "image": image, "uid": os.geteuid(), "harness_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
               "passed": False, "production_tunnel_proven": False, "application_proven": False,
               "fixture_root": str(root), "events": events}
    (root/"intent.json").write_text(json.dumps({"operation": operation, "network": network,
        "containers": names, "label": label, "image": image}, sort_keys=True)+"\n")
    (root/"node.py").write_text(NODE)
    (root/"chisel").touch(mode=0o400)  # mount point inside the read-only fixture bind
    credentials = {mode: mode + "-fixture:" + secrets.token_urlsafe(24) for mode in ("app", "home")}
    (root/"fixture-credentials.json").write_text(json.dumps(credentials))
    os.chmod(root/"fixture-credentials.json", 0o600)
    reverse_acl = [r"^R:127\.0\.0\." + str(i) + ":50142$" for i in (1,2,3)]
    ssh_acl = r"^R:127\.0\.0\.1:2222$"
    normal_acl = [r"^127\.0\.0\.2:50142$", r"^127\.0\.0\.3:50142$"]
    deadline = time.monotonic() + 80
    created = {}

    def command(args, check=True):
        result = subprocess.run(["docker", *args], capture_output=True, text=True, timeout=20)
        require(not check or result.returncode == 0, "fixture Docker operation failed: " + args[0])
        return result

    def logs(mode):
        result = command(["logs", names[mode]])
        return result.stdout + result.stderr

    def wait_for(name, predicate):
        end = min(deadline, time.monotonic()+10)
        while time.monotonic() < end:
            if predicate():
                return
            time.sleep(0.1)
        raise RuntimeError(name + " deadline")

    def authfile(normal):
        values = {credentials["app"]: reverse_acl,
                  credentials["home"]: [ssh_acl, *(normal_acl if normal else [])]}
        pending = root/"users.pending"
        with pending.open("w") as handle:
            os.chmod(pending, 0o600)
            json.dump(values, handle);handle.flush();os.fsync(handle.fileno())
        os.replace(pending, root/"users.json")
        fd=os.open(root,os.O_DIRECTORY|os.O_RDONLY)
        try:os.fsync(fd)
        finally:os.close(fd)

    def start(mode, fp=None):
        args=["run","-d","--name",names[mode],"--label",label,"--network",network,
              "--network-alias", "vps" if mode=="server" else mode,
              "--user",str(os.geteuid())+":"+str(os.getegid()),"--cap-drop","ALL",
              "--security-opt","no-new-privileges","--read-only","--pids-limit","64",
              "--memory","128m","--cpus","1","--tmpfs","/tmp:rw,nosuid,nodev,mode=1777,size=16m",
              "--mount","type=bind,src="+str(root)+",dst=/fixture,readonly",
              "--mount","type=bind,src="+str(binary)+",dst=/fixture/chisel,readonly",
              image,"/usr/bin/python3.12","-B","/fixture/node.py",mode]
        if fp:args.append(fp)
        created[mode]=command(args).stdout.strip()
        events.append({"action":"created","mode":mode,"container_id":created[mode]})

    def probe(mode, address, port, token):
        result=command(["exec",names[mode],"/usr/bin/python3.12","-I","-B","-c",PROBE,address,str(port),token])
        return json.loads(result.stdout)["reply"]

    def proof(mode, address, port, prefix, label_name):
        token=label_name+"-"+secrets.token_hex(12)
        require(probe(mode,address,port,token)==prefix+token+"\n", label_name+" forwarding failed")
        events.append({"action":"forwarded_once","label":label_name,"token":token})
        return token

    try:
        authfile(True)
        command(["network","create","--internal","--label",label,network])
        start("server")
        wait_for("server",lambda:"Listening" in logs("server"))
        match=re.search(r"Fingerprint ([A-Za-z0-9+/]{43}=)",logs("server"))
        require(match is not None,"fixture fingerprint unavailable")
        start("app",match[1]);start("home",match[1])
        wait_for("both authenticated clients",lambda:"Connected" in logs("app") and "Connected" in logs("home"))
        require(logs("home").count("Connected")==1 and logs("app").count("Connected")==1,
                "fixture unexpectedly reconnected")
        tokens=[proof("home",address,50142,"APP:","home-"+address) for address in ("127.0.0.2","127.0.0.3")]
        ssh_tokens=[proof("server","127.0.0.1",2222,"SSH:","ssh-before")]
        offset=len(logs("server"))
        authfile(False)
        denied=[]
        def revoked():
            token="denied-observation-"+secrets.token_hex(12)
            reply=probe("home","127.0.0.2",50142,token)
            if reply is None and "Denied connection to 127.0.0.2:50142 (ACL)" in logs("server")[offset:]:
                denied.append(token);return True
            return False
        wait_for("normal-destination ACL refresh",revoked)
        token="denied-role-three-"+secrets.token_hex(12)
        require(probe("home","127.0.0.3",50142,token) is None,"reverse ACL unexpectedly authorized normal forwarding")
        denied.append(token)
        ssh_tokens.append(proof("server","127.0.0.1",2222,"SSH:","ssh-with-normal-revoked"))
        authfile(True)
        def restored():
            token="restore-observation-"+secrets.token_hex(12)
            return probe("home","127.0.0.2",50142,token)=="APP:"+token+"\n"
        wait_for("normal ACL restoration",restored)
        tokens += [proof("home",address,50142,"APP:","restored-"+address)
                   for address in ("127.0.0.2","127.0.0.3")]
        ssh_tokens.append(proof("server","127.0.0.1",2222,"SSH:","ssh-after"))
        app_arrivals=Counter(re.findall(r"^ARRIVAL (.+)$",logs("app"),re.M))
        home_arrivals=Counter(re.findall(r"^ARRIVAL (.+)$",logs("home"),re.M))
        require(all(app_arrivals[token]==1 for token in tokens)
                and all(home_arrivals[token]==1 for token in ssh_tokens)
                and all(app_arrivals[token]==0 for token in denied),
                "duplicate or denied backend arrival")
        require(logs("home").count("Connected")==1 and logs("app").count("Connected")==1,
                "ACL proof required a client reconnection")
        receipt.update(passed=True, distinct_network_namespaces=3, both_home_forwards=True,
                       reverse_only_acl_refuses_normal_forward=True,
                       retained_home_authenticated_connections=1, original_reverse_connections=1,
                       ssh_return_retained=True, denied_probe_backend_arrivals=0,
                       duplicate_accepted_probe_arrivals=0, normal_acl_reload_without_restart=True)
    except Exception as exc:
        receipt["failure"]={"type":type(exc).__name__,"message":str(exc)}
    finally:
        cleaned=[]
        for mode,name in reversed(list(names.items())):
            observed=command(["inspect",name],False)
            if observed.returncode==0:
                value=json.loads(observed.stdout)[0]
                require(value.get("Config",{}).get("Labels",{}).get("mastermind.hermes-home-proof")==operation,
                        "foreign fixture container refused")
                content=logs(mode)
                (root/(mode+".log")).write_text(content)
                command(["rm","-f",name])
            verify=command(["inspect",name],False)
            cleaned.append(verify.returncode!=0 and "no such" in verify.stderr.lower())
        observed=command(["network","inspect",network],False)
        if observed.returncode==0:
            value=json.loads(observed.stdout)[0]
            require(value.get("Labels",{}).get("mastermind.hermes-home-proof")==operation,
                    "foreign fixture network refused")
            command(["network","rm",network])
        verify=command(["network","inspect",network],False)
        receipt["owned_containers_removed"]=all(cleaned)
        receipt["owned_network_removed"]=verify.returncode!=0 and "not found" in verify.stderr.lower()
        receipt["passed"]=receipt["passed"] and receipt["owned_containers_removed"] and receipt["owned_network_removed"]
        for name in ("users.json","users.pending","fixture-credentials.json"):
            (root/name).unlink(missing_ok=True)
        receipt["synthetic_credentials_removed"]=not (root/"fixture-credentials.json").exists() and not (root/"users.json").exists()
        receipt["logs"]={p.name:{"sha256":hashlib.sha256(p.read_bytes()).hexdigest(),"bytes":p.stat().st_size} for p in root.glob("*.log")}
        (root/"result.json").write_text(json.dumps(receipt,indent=2,sort_keys=True)+"\n")
    return receipt


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary",required=True)
    parser.add_argument("--expected-sha256",required=True)
    parser.add_argument("--image",required=True)
    parser.add_argument("--fixture-root",required=True)
    args=parser.parse_args()
    receipt=execute(args.binary,args.expected_sha256,args.image,args.fixture_root)
    print(json.dumps(receipt,sort_keys=True))
    return 0 if receipt["passed"] else 1


if __name__=="__main__":
    raise SystemExit(main())

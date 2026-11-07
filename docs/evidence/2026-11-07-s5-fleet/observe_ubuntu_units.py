import os,pwd,pathlib,stat,hashlib,json,datetime,subprocess,socket,sys,math
expected_home,expected_host=sys.argv[1:]
owner=pwd.getpwuid(os.geteuid())
out={"observed_at":datetime.datetime.now(datetime.timezone.utc).isoformat(),"host":socket.gethostname(),"uid":os.geteuid(),"user":owner.pw_name,"home":owner.pw_dir,"effect_state":"NOT_APPLIED","reclaimed_bytes":0}
if owner.pw_dir!=expected_home or socket.gethostname()!=expected_host:
 out["state"]="IDENTITY_MISMATCH"; print(json.dumps(out)); raise SystemExit(0)
files=[".config/mastermind/fabric-storage-reserve.json",".config/systemd/user/mastermind-linux-hygiene.service",".config/systemd/user/mastermind-linux-hygiene.timer",".local/lib/mastermind/storage-cleanup/linux_hygiene.py"]
out["files"]={}
for rel in files:
 p=pathlib.Path(owner.pw_dir)/rel
 try:
  fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW)
  try:
   st=os.fstat(fd)
   if not stat.S_ISREG(st.st_mode) or st.st_size>2000000: raise ValueError("not_bounded_regular_file")
   b=os.read(fd,st.st_size+1)
  finally: os.close(fd)
  row={"uid":st.st_uid,"mode":oct(stat.S_IMODE(st.st_mode)),"inode":st.st_ino,"sha256":hashlib.sha256(b).hexdigest(),"owner_uid_and_no_group_other_write":st.st_uid==os.geteuid() and not(st.st_mode&0o022)}
  if rel.endswith("reserve.json"):
   d=json.loads(b); v=d.get("internal_floor_gib"); row["internal_floor_gib"]=v if type(v) in (int,float) and math.isfinite(v) and v>0 else None
  out["files"][rel]=row
 except (OSError,ValueError,TypeError) as e: out["files"][rel]={"state":"UNVERIFIED","reason":type(e).__name__}
out["filesystems"]={}
for p in ("/",owner.pw_dir):
 st=os.statvfs(p); out["filesystems"][p]={"available_bytes":st.f_bavail*st.f_frsize,"total_bytes":st.f_blocks*st.f_frsize,"free_bytes":st.f_bfree*st.f_frsize}
runtime="/run/user/"+str(os.geteuid()); bus=pathlib.Path(runtime)/"bus"
try:
 st=bus.stat(); valid=stat.S_ISSOCK(st.st_mode) and st.st_uid==os.geteuid()
except OSError: valid=False
out["same_uid_bus_verified"]=valid
if valid:
 env=dict(os.environ,XDG_RUNTIME_DIR=runtime,DBUS_SESSION_BUS_ADDRESS="unix:path="+str(bus))
 out["units"]={}
 for unit,props in [("mastermind-linux-hygiene.timer",["UnitFileState","ActiveState","SubState","NextElapseUSecRealtime","LastTriggerUSec","FragmentPath","DropInPaths","Unit"]),("mastermind-linux-hygiene.service",["UnitFileState","ActiveState","SubState","Result","ExecMainStatus","ExecMainCode","FragmentPath","DropInPaths","ExecStart","ExecMainStartTimestamp","ExecMainExitTimestamp","NRestarts"])]:
  r=subprocess.run(["systemctl","--user","show",unit,"--no-pager"]+["--property="+x for x in props],env=env,capture_output=True,text=True,timeout=10)
  out["units"][unit]={"rc":r.returncode,"properties":dict(line.split("=",1) for line in r.stdout.splitlines() if "=" in line),"diagnostic":r.stderr[:256]}  # bounded stderr truncation for the evidence record
else: out["unit_state"]="UNVERIFIED_NO_OWNER_BUS"
print(json.dumps(out,sort_keys=True))

"""Frozen future Claude principal capability projection descriptors.

These values describe an inert, explicitly loaded source candidate. They grant
no admission; the default policy has neither these grants nor the profile.
The existing ExecutionCapabilityRegistry remains the sole policy parser.
"""
RICH_CLAUDE_PRINCIPAL_PROFILE_ID = "principal.claude.coo.rich.v1"
EXECUTIVE_COO_MCP_CAPABILITY_ID = "executive-coo-mcp-v1"
EXECUTIVE_COO_MCP_CONFIG_NAME = "mastermindExecutiveCoo"
EXECUTIVE_COO_MCP_URL = "http://127.0.0.1:8444/mcp"
EXECUTIVE_COO_MCP_SERVER_IDENTITY = "mastermind-executive-coo"
EXECUTIVE_COO_MCP_SERVER_VERSION = "1.0.0"
EXECUTIVE_COO_MCP_TOOL_SCHEMA_DIGEST = (
    "8d4ff58a30c02b717788b80fdfd1c5b8b35493dc11dd76cac351cde7b4509d72"
)
EXECUTIVE_COO_MCP_ENABLED_TOOLS = (
    "executive_fabric",
    "executive_inbox",
    "executive_mandate",
    "executive_state",
    "principal_intent_status",
    "submit_principal_intent",
)

PRINCIPAL_COMPANY_MCP_CAPABILITY_ID = "company-dialogue-principal-mcp-v1"
PRINCIPAL_COMPANY_MCP_CONFIG_NAME = "mastermindCompanyDialoguePrincipal"
PRINCIPAL_COMPANY_MCP_COMMAND = "/usr/bin/python3"
PRINCIPAL_COMPANY_MCP_SERVER_IDENTITY = "mastermind-company-dialogue-principal-mcp"
PRINCIPAL_COMPANY_MCP_SERVER_VERSION = "0.1.0"
PRINCIPAL_COMPANY_MCP_TOOL_SCHEMA_DIGEST = (
    "d45c0f8fe2451c726757c42be729e0e49fc5b2637c33efc97dee00168fab7abd"
)
PRINCIPAL_COMPANY_MCP_ENABLED_TOOLS = (
    "continue",
    "read_thread",
    "ruling",
    "stop",
)
PRINCIPAL_COMPANY_MCP_BOOTSTRAP = r'''import hashlib,json,os,pathlib,re,stat,subprocess
R=pathlib.Path("/Library/Application Support/MastermindExecutive")
C=R/"config/company-dialogue-principal-edge.json"
E={"PATH":"/usr/bin:/bin","LANG":"en_US.UTF-8"}
def sealed(p,d=False):
 for n in (p,*p.parents):
  i=n.lstat(); D=d or n!=p
  if i.st_uid!=0 or ((n==p or n==R or R in n.parents) and i.st_gid!=0) or i.st_mode&0o022 or stat.S_ISLNK(i.st_mode) or not (stat.S_ISDIR(i.st_mode) if D else stat.S_ISREG(i.st_mode)) or (not D and i.st_nlink!=1): raise ValueError()
  if b"+" in subprocess.check_output(["/usr/bin/stat","-f","%Sp",str(n)],env=E): raise ValueError()
try:
 sealed(C)
 if stat.S_IMODE(C.stat().st_mode)!=0o444: raise ValueError()
 v=json.loads(C.read_bytes()); S=v["release_sha"]
 if set(v)!={"schema","release_sha","control_uid","worker_uid","runtime_entry_sha256","principal_entry_sha256","receipt_sha256"} or v["schema"]!="mastermind.company_dialogue_principal_edge/v1" or type(S)!=str or re.fullmatch("[0-9a-f]{40}",S) is None or type(v["worker_uid"])!=int or v["worker_uid"]<=0 or os.geteuid()!=v["worker_uid"]: raise ValueError()
 P=R/"releases"/S/"ops/executive_os/company_dialogue_principal_edge.py"; sealed(P)
 if hashlib.sha256(P.read_bytes()).hexdigest()!=v["principal_entry_sha256"]: raise ValueError()
 B=pathlib.Path("/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12"); sealed(B)
 os.execve(B,[str(B),"-I","-S","-B",str(P),"stdio"],E)
except (KeyError,OSError,TypeError,UnicodeError,ValueError):
 raise SystemExit("Principal Company edge bootstrap refused")
'''
PRINCIPAL_COMPANY_MCP_ARGS = (
    "-I",
    "-S",
    "-B",
    "-c",
    PRINCIPAL_COMPANY_MCP_BOOTSTRAP,
)
RICH_CLAUDE_PRINCIPAL_MCP_IDS = tuple(
    sorted(
        (
            EXECUTIVE_COO_MCP_CAPABILITY_ID,
            PRINCIPAL_COMPANY_MCP_CAPABILITY_ID,
        )
    )
)

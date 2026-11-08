"""Test-only exact incumbent read/recipe child admission, never production policy.

Root's source-test ruling permits two unchanged isolated entry points over owned
Git fixtures. This does not permit arbitrary Python, scripts, provider or host.
"""
from pathlib import Path
import hashlib
import math
import os
import re
import sys
from ops.executive_os.capacity_source_contract import PYTHON_BINARY

PINNED = {
 'agentos_project_knowledge_recipe_entry.py':'80b954460662c4eac7c87c2d752cdcba5504e260084b68f9ee6cbfc3c82c6534',
 'agentos_project_knowledge_entry.py':'52ca6fada4482f5ef0b24e6c0dc099e1f25c0732d7cf605b5ecb64b04f6845c3',
}

def allows_fixed_child(executable,argv,cwd,env,*,code_root,owned_root):
 try:
  root=Path(code_root).resolve();owned=Path(owned_root).resolve()
  if Path(executable)!=Path(PYTHON_BINARY) or type(argv) not in (list,tuple) or len(argv)<12 or any(type(v) is not str for v in argv):return False
  if Path(argv[0])!=Path(PYTHON_BINARY) or argv[1:3]!=['-I','-B'] or Path(cwd).resolve()!=root:return False
  script=Path(argv[3]);name=script.name
  if name not in PINNED or script!=root/'scripts'/name or hashlib.sha256(script.read_bytes()).hexdigest()!=PINNED[name]:return False
  # Exact finite flag order constructed by the installed collector.
  if argv[4]!='--macro-root' or argv[6]!='--expected-macro-sha':return False
  macro=Path(argv[5]);
  if not macro.is_absolute() or not macro.resolve().is_relative_to(owned) or not macro.is_dir() or not re.fullmatch('[0-9a-f]{40}',argv[7]):return False
  if name=='agentos_project_knowledge_recipe_entry.py':
   if len(argv)!=16 or argv[8]!='--mode' or argv[9] not in {'prepare','restore'} or argv[10]!='--timeout':return False
   timeout=argv[11];tail=12
  else:
   if len(argv) not in (18,22) or argv[8]!='--operation' or argv[9] not in {'project_knowledge_catalogue','project_knowledge_source','project_knowledge_memory'} or argv[10]!='--work-ref' or not re.fullmatch('WS:[A-Z0-9]+(?:-[A-Z0-9]+)*',argv[11]) or argv[12]!='--timeout':return False
   timeout=argv[13];tail=14
   if argv[9]=='project_knowledge_source':
    if len(argv)!=22 or argv[14]!='--source-ref' or not re.fullmatch(r'project-file\.v1\.[0-9a-f]{64}',argv[15]) or argv[16]!='--expected-revision' or not re.fullmatch('[0-9a-f]{40}',argv[17]):return False
    tail=18
   elif len(argv)!=18:return False
  value=float(timeout)
  if not math.isfinite(value) or not 0<value<=15:return False
  if argv[tail]!='--code-root' or argv[tail+2]!='--code-commit' or not re.fullmatch('[0-9a-f]{40}',argv[tail+3]):return False
  code=Path(argv[tail+1])
  if not code.is_absolute() or not code.resolve().is_relative_to(owned) or not code.is_dir():return False
  git=code/'.git';head=git/'HEAD'
  if not git.is_dir() or git.is_symlink() or head.is_symlink() or head.read_text().strip()!=argv[tail+3]:return False
  from integrations.executive_mcp.installed import _installed_child_env
  return type(env) is dict and env==_installed_child_env(code_root=root,macro_root=macro)
 except (ValueError,TypeError,KeyError,IndexError,OSError):return False

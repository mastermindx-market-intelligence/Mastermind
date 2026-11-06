from pathlib import Path
import copy
import sys
import pytest
from tests.project_draft_files_child_guard import PINNED,allows_fixed_child
from ops.executive_os.capacity_source_contract import PYTHON_BINARY,BASE_PYTHON_BINARY
from integrations.executive_mcp.installed import _installed_child_env
ROOT=Path(__file__).parents[1]

def operands(tmp_path,kind='recipe'):
 macro=tmp_path/'data';macro.mkdir();code=tmp_path/'code';code.mkdir();(code/'.git').mkdir();(code/'.git/HEAD').write_text('b'*40+'\n')
 args=[str(PYTHON_BINARY),'-I','-B',str(ROOT/'scripts'/('agentos_project_knowledge_recipe_entry.py' if kind=='recipe' else 'agentos_project_knowledge_entry.py')),'--macro-root',str(macro),'--expected-macro-sha','a'*40]
 args+=['--mode','prepare','--timeout','5'] if kind=='recipe' else ['--operation','project_knowledge_catalogue','--work-ref','WS:FILES','--timeout','5']
 args+=['--code-root',str(code),'--code-commit','b'*40]
 return args,_installed_child_env(code_root=ROOT,macro_root=macro)

@pytest.mark.parametrize('kind',['recipe','read'])
def test_only_exact_pinned_isolated_children_over_owned_code_and_data(tmp_path,kind):
 argv,env=operands(tmp_path,kind)
 assert allows_fixed_child(str(PYTHON_BINARY),argv,ROOT,env,code_root=ROOT,owned_root=tmp_path)
 assert not allows_fixed_child(str(PYTHON_BINARY),argv,ROOT,{**env,'OPENAI_API_KEY':'synthetic-never-a-secret'},code_root=ROOT,owned_root=tmp_path)
 for index,value in [(1,'-c'),(3,str(ROOT/'scripts/ceo_boot_packet.py')),(5,str(ROOT)),(7,'bad'),(len(argv)-3,str(ROOT)),(len(argv)-1,'c'*39)]:
  wrong=list(argv);wrong[index]=value
  assert not allows_fixed_child(str(PYTHON_BINARY),wrong,ROOT,env,code_root=ROOT,owned_root=tmp_path)
 assert not allows_fixed_child(str(PYTHON_BINARY),[*argv,'--provider','anything'],ROOT,env,code_root=ROOT,owned_root=tmp_path)
 assert not allows_fixed_child('/usr/bin/false',argv,ROOT,env,code_root=ROOT,owned_root=tmp_path)
 base=list(argv);base[0]=str(BASE_PYTHON_BINARY)
 assert not allows_fixed_child(base[0],base,ROOT,env,code_root=ROOT,owned_root=tmp_path)
 assert not allows_fixed_child(str(PYTHON_BINARY),argv,tmp_path,env,code_root=ROOT,owned_root=tmp_path)

def test_recipe_pin_requires_current_exact_source_in_owned_temp_code_root(tmp_path,monkeypatch):
 data=(ROOT/'scripts'/'agentos_project_knowledge_recipe_entry.py').read_bytes()
 def fixture(name,payload):
  base=tmp_path/name;code=base/'code';(code/'scripts').mkdir(parents=True)
  (code/'scripts'/'agentos_project_knowledge_recipe_entry.py').write_bytes(payload)
  (code/'.git').mkdir();(code/'.git/HEAD').write_text('b'*40+'\n')
  macro=base/'data';macro.mkdir()
  code=code.resolve();macro=macro.resolve()
  argv=[str(PYTHON_BINARY),'-I','-B',str(code/'scripts'/'agentos_project_knowledge_recipe_entry.py'),'--macro-root',str(macro),'--expected-macro-sha','a'*40,'--mode','prepare','--timeout','5','--code-root',str(code),'--code-commit','b'*40]
  return argv,_installed_child_env(code_root=code,macro_root=macro),code
 argv,env,code=fixture('pin',data)
 assert allows_fixed_child(str(PYTHON_BINARY),argv,code,env,code_root=code,owned_root=tmp_path)
 drift_argv,drift_env,drift_code=fixture('drift',data+b'# drifted\n')
 assert not allows_fixed_child(str(PYTHON_BINARY),drift_argv,drift_code,drift_env,code_root=drift_code,owned_root=tmp_path)
 monkeypatch.setitem(PINNED,'agentos_project_knowledge_recipe_entry.py','8fe367f4b089641bfc26a007000532799f4d1d18000605a2564e135f23f97251')
 assert not allows_fixed_child(str(PYTHON_BINARY),argv,code,env,code_root=code,owned_root=tmp_path)

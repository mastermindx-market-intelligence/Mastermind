"""Causal mutations of disposable emitted modules; always restore exact bytes."""
import argparse
import json
from pathlib import Path
import subprocess
from owned_command import run

parser=argparse.ArgumentParser();parser.add_argument('--upstream',required=True,type=Path)
args=parser.parse_args();root=args.upstream.resolve()
manager=root/'dist/search-manager.js';handler=root/'dist/handlers/search-handlers.js'
mutations=[
 ('thread budget',manager,"['--no-config', '--threads', '2']","['--no-config', '--threads', '3']",'AssertionError'),
 ('live-work admission',manager,'this.admissions.size >= 2','this.admissions.size >= 99','AssertionError'),
 ('preflight permit retention',manager,'admission.stopped = true;','admission.stopped = true; admission.release();','deadline must not release unsettled preflight'),
 ('late preflight fence',manager,"if (admission.stopped)\n            throw new SearchAdmissionError('search_deadline');",'if (false) throw new Error("disabled fence");','late preflight spawned a search'),
 ('initial cap flag',handler,'maxResultsReached: limits.maxResultsReached,','maxResultsReached: false,','AssertionError'),
 ('initial cap disclosure',handler,'output += `\\nSearch result limit reached. Results are incomplete.`;','output += "";','result limit reached'),
 ('initial deadline flag',handler,'timedOut: limits.timedOut,','timedOut: false,','AssertionError'),
]
runner="""import {spawnSync} from 'node:child_process';import {createTestEnv} from './test/helpers/test-env.js';
const t=createTestEnv();try{const r=spawnSync(process.execPath,['test/test-issue1027-admission.mjs'],{env:t.env,stdio:'inherit',timeout:15000});process.exitCode=r.status??91;}finally{t.cleanup();}"""
results=[]
for index,(name,target,before,after,discriminator) in enumerate(mutations):
 original=target.read_bytes();text=original.decode();assert before in text,name
 log=root.parent/f'v4-mutation-{index}.log'
 try:
  target.write_text(text.replace(before,after,1))
  try:run(['node','--input-type=module','-e',runner],root,log,timeout=20)
  except subprocess.CalledProcessError:
   output=log.read_text();assert discriminator in output,(name,output[-2000:])
   results.append({'mutation':name,'status':'DETECTED','discriminator':discriminator})
  else:raise AssertionError('mutation survived: '+name)
 finally:target.write_bytes(original)
(root.parent/'v4-mutation-results.json').write_text(json.dumps(results,indent=2)+'\n')
print(json.dumps({'detected':len(results),'total':len(mutations),'compiledBytesRestored':True}))

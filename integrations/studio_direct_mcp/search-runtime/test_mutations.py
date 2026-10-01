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
mutations = [(*item, "test-issue1027-admission.mjs") for item in mutations]
owner = root/"dist/tools/filesystem.js"
mutations += [
 ("actual validation settlement",manager,"await admission.validationSettled;","await Promise.resolve();","non-cancelling internal timeout released live work","test-issue1027-validation-owner.mjs"),
 ("parallel validation settlement",owner,"pendingWork?.push(lookup);","void lookup;","first path answer released parallel lookup work","test-issue1027-validation-owner.mjs"),
 ("effective early-termination identity",manager,"earlyTermination: options.earlyTermination !== false,","earlyTermination: options.earlyTermination,","same effective true produced different admission","test-issue1027-validation-owner.mjs"),
 ("explicit exhaustive execution",manager,"session.options.earlyTermination &&","true &&","AssertionError","test-issue1027-validation-owner.mjs"),
]
runner="""import {spawnSync} from 'node:child_process';import {createTestEnv} from './test/helpers/test-env.js';
const t=createTestEnv();try{const r=spawnSync(process.execPath,['test/TEST_FILE'],{env:t.env,stdio:'inherit',timeout:15000});process.exitCode=r.status??91;}finally{t.cleanup();}"""
results=[]
for index,(name,target,before,after,discriminator,test) in enumerate(mutations):
 original=target.read_bytes();text=original.decode();assert before in text,name
 log=root.parent/f'v5-mutation-{index}.log'
 try:
  target.write_text(text.replace(before,after))
  try:run(['node','--input-type=module','-e',runner.replace('TEST_FILE',test)],root,log,timeout=20)
  except subprocess.CalledProcessError:
   output=log.read_text();assert discriminator in output,(name,output[-2000:])
   results.append({'mutation':name,'status':'DETECTED','discriminator':discriminator})
  else:raise AssertionError('mutation survived: '+name)
 finally:target.write_bytes(original)
(root.parent/'v5-mutation-results.json').write_text(json.dumps(results,indent=2)+'\n')
print(json.dumps({'detected':len(results),'total':len(mutations),'compiledBytesRestored':True}))

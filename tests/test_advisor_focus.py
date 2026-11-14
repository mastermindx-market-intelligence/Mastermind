"""Network-free lifecycle tests of the production Advisor focus functions (Node required)."""
import json
import os
from pathlib import Path
import subprocess
import unittest

SOURCE = Path(os.environ.get('ADVISOR_SOURCE', Path(__file__).resolve().parents[1] / 'app/static/chat.js'))

class AdvisorFocusTests(unittest.TestCase):
    def run_case(self, actions, empty=False):
        source = SOURCE.read_text()
        start = source.index('  function open() {')
        prefix = source[:start]
        declaration = '  var focusGeneration = 0;\n'
        if prefix.endswith(declaration):
            start -= len(declaration)
        end = source.index('  launch.onclick = open;', start) + len('  launch.onclick = open;')
        code = r'''
const vm = require('node:vm');
const config = JSON.parse(process.argv[1]);
const classes = new Set(), timers = [];
let focuses = 0, hydrated = 0, paperClosed = 0;
const context = {
  document: {body: {classList: {add: x=>classes.add(x), remove: x=>classes.delete(x), contains: x=>classes.has(x)}}},
  body: {children: config.empty ? [] : [1]},
  rehydrate(){hydrated++;context.body.children.push(1);},
  input: {focus(){focuses++;}},
  closePaper(){paperClosed++;}, launch: {},
  setTimeout(fn, delay){timers.push({fn, delay});}
};
vm.runInNewContext(config.source + ';globalThis.doClose=close;', context);
const counts = [];
for (const action of config.actions) {
 if(action==='open')context.launch.onclick();
 else if(action==='close')context.doClose();
 else if(action==='hide')classes.delete('bc-open');
 else timers[action].fn();
 counts.push(focuses);
}
console.log(JSON.stringify({counts, hydrated, paperClosed, open:classes.has('bc-open'), delays:timers.map(t=>t.delay)}));
'''
        result = subprocess.run(['node', '-e', code, json.dumps({'source': source[start:end], 'actions': actions, 'empty': empty})], capture_output=True, text=True, check=True)
        return json.loads(result.stdout)

    def test_open_focuses_only_after_delay(self):
        r=self.run_case(['open', 0]); self.assertEqual(r['counts'],[0,1]); self.assertEqual(r['delays'],[120]); self.assertTrue(r['open'])
    def test_close_before_delay_never_focuses_hidden_input(self):
        r=self.run_case(['open','close',0]); self.assertEqual(r['counts'],[0,0,0]); self.assertFalse(r['open']); self.assertEqual(r['paperClosed'],1)
    def test_reopen_retires_old_callback(self):
        self.assertEqual(self.run_case(['open','close','open',0,1])['counts'],[0,0,0,0,1])
    def test_old_callback_after_new_callback_is_inert(self):
        self.assertEqual(self.run_case(['open','close','open',1,0])['counts'],[0,0,0,1,1])
    def test_repeated_open_uses_latest_callback(self):
        self.assertEqual(self.run_case(['open','open',0,1])['counts'],[0,0,0,1])
    def test_many_closed_openings_do_not_focus(self):
        self.assertEqual(self.run_case(['open','close','open','close',1,0])['counts'],[0]*6)
    def test_visibility_class_is_required(self):
        self.assertEqual(self.run_case(['open','hide',0])['counts'],[0,0,0])
    def test_close_after_focus_preserves_paper_cleanup(self):
        r=self.run_case(['open',0,'close']);self.assertEqual(r['counts'],[0,1,1]);self.assertEqual(r['paperClosed'],1)
    def test_empty_body_rehydrates_once(self):
        self.assertEqual(self.run_case(['open','close','open',1],empty=True)['hydrated'],1)
    def test_populated_body_does_not_rehydrate(self):
        self.assertEqual(self.run_case(['open',0])['hydrated'],0)

if __name__ == '__main__': unittest.main()

"""Exercise the served Advisor's exact keydown registration without a provider.

The Node VM exposes only a recording input and a send spy. It does not load the
widget, fetch, storage, a DOM, or browser/OS IME machinery. This is handler-level
proof; native keyboard and full-widget acceptance remain separate.
"""

import json
from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "app" / "static" / "chat.js"
SCRIPT = r"""
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const [sourcePath, encodedEvents] = process.argv.slice(1);
const source = fs.readFileSync(sourcePath, 'utf8');
const registrations = source.match(/input\.addEventListener\("keydown",\s*function\s*\(e\)\s*\{[\s\S]*?\}\);/g) || [];
assert.equal(registrations.length, 1, 'Use the one actual Advisor keydown registration');
let listener;
const sent = [];
const input = {
  value: '',
  addEventListener(type, callback) {
    assert.equal(type, 'keydown');
    listener = callback;
  },
};
vm.runInNewContext(registrations[0], {
  input,
  send() { sent.push(input.value); },
}, {timeout: 1000});
const prevented = [];
for (const event of JSON.parse(encodedEvents)) {
  const {draft, ...flags} = event;
  input.value = draft;
  let count = 0;
  listener({...flags, preventDefault() { count++; }});
  prevented.push(count);
  assert.equal(input.value, draft, 'Keyboard handling must not edit the unsent draft');
}
process.stdout.write(JSON.stringify({sent, prevented}));
"""


def dispatch(events):
    completed = subprocess.run(
        ["node", "-e", SCRIPT, str(SOURCE), json.dumps(events)],
        check=True, capture_output=True, text=True, timeout=10,
    )
    return json.loads(completed.stdout)


class AdvisorKeyboardTests(unittest.TestCase):
    def test_composition_enter_does_not_send_or_cancel_commit(self):
        for draft in ("Unsent draft", "尚未发送的研究问题"):
            with self.subTest(draft=draft):
                self.assertEqual(dispatch([{
                    "draft": draft, "key": "Enter", "isComposing": True,
                }]), {"sent": [], "prevented": [0]})

    def test_legacy_composition_enter_does_not_send(self):
        self.assertEqual(dispatch([{
            "draft": "研究", "key": "Enter", "isComposing": False,
            "keyCode": 229,
        }]), {"sent": [], "prevented": [0]})

    def test_legacy_composition_without_is_composing_property(self):
        self.assertEqual(dispatch([{
            "draft": "研究", "key": "Enter", "keyCode": 229,
        }]), {"sent": [], "prevented": [0]})

    def test_plain_enter_preserves_existing_send_gesture(self):
        for draft in ("Unsent draft", "已完成的研究问题"):
            with self.subTest(draft=draft):
                self.assertEqual(dispatch([{
                    "draft": draft, "key": "Enter", "keyCode": 13,
                    "isComposing": False,
                }]), {"sent": [draft], "prevented": [1]})

    def test_ordinary_enter_without_optional_keyboard_properties(self):
        self.assertEqual(dispatch([{"draft": "Ready", "key": "Enter"}]),
                         {"sent": ["Ready"], "prevented": [1]})

    def test_shift_enter_keeps_newline(self):
        self.assertEqual(dispatch([{
            "draft": "Two lines", "key": "Enter", "shiftKey": True,
        }]), {"sent": [], "prevented": [0]})

    def test_other_keys_do_not_send(self):
        events = [{"draft": "Keep draft", "key": key}
                  for key in ("Escape", "Process", "a", " ")]
        self.assertEqual(dispatch(events), {"sent": [], "prevented": [0] * 4})

    def test_explicit_enter_after_composition_sends_completed_draft_once(self):
        self.assertEqual(dispatch([
            {"draft": "yan", "key": "Enter", "isComposing": True},
            {"draft": "研究", "key": "Enter", "isComposing": False,
             "keyCode": 13},
        ]), {"sent": ["研究"], "prevented": [0, 1]})

    def test_explicit_enter_after_legacy_composition_sends_once(self):
        self.assertEqual(dispatch([
            {"draft": "yan", "key": "Enter", "keyCode": 229},
            {"draft": "研究", "key": "Enter", "keyCode": 13},
        ]), {"sent": ["研究"], "prevented": [0, 1]})

    def test_existing_modified_enter_behavior_is_unchanged(self):
        for modifier in ("ctrlKey", "metaKey", "altKey"):
            with self.subTest(modifier=modifier):
                self.assertEqual(dispatch([{
                    "draft": "Ready", "key": "Enter", modifier: True,
                }]), {"sent": ["Ready"], "prevented": [1]})


if __name__ == "__main__":
    unittest.main()

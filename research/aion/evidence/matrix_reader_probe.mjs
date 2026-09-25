// Exact existing Terminal reader over a roundtrip through the existing Macro
// immutable-write primitive and the existing FakeR2. No real publication.
import assert from 'node:assert/strict';
import { readFileSync, writeFileSync } from 'node:fs';
import { isMatrixDocForRoot } from './matrixDoc.ts';
const rows = [];
for (const root of ['SPY','QQQ']) {
  const value = JSON.parse(readFileSync(new URL(`./${root}-roundtrip.json`, import.meta.url), 'utf8'));
  assert.equal(isMatrixDocForRoot(value, root), true);
  assert.equal(isMatrixDocForRoot(value, root === 'SPY' ? 'QQQ' : 'SPY'), false);
  rows.push({ root, valid_original_root:true, wrong_root_refused:true });
}
const receipt = {evidence_class:'exact_reader_synthetic_roundtrip', rows,
  terminal_source:'87969fb4aff5836410ffd166cc39289b562a41bc',
  production_proof:false, history_selector_implemented:false};
writeFileSync(new URL('./matrix_reader_result.json', import.meta.url), JSON.stringify(receipt,null,2)+'\n');
console.log(JSON.stringify(receipt));

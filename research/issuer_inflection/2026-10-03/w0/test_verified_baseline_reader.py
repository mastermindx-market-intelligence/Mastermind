"""Adversarial read-boundary tests; no network, services or owner mutations."""
from __future__ import annotations
from copy import deepcopy
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import verified_baseline_reader as reader
from baseline_replay import canonical, digest

ROOT = Path(__file__).resolve().parent
ORIGINAL = ROOT / "evidence/baseline-replay"

class VerifiedReaderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="i3-reader-test-")
        self.root = Path(self.temp.name) / "evidence"
        shutil.copytree(ORIGINAL, self.root)
    def tearDown(self):
        self.temp.cleanup()
    def write_json(self, name, value):
        (self.root / name).write_bytes(canonical(value))
    def refuse(self, case="later_admission_refusal"):
        with self.assertRaises(reader.ReaderRefusal): reader.load_verified(case, self.root)
    def corrupt_comparison(self, action, rehash=False):
        name="later_admission_refusal.comparison.json"
        obj=json.loads((self.root / name).read_bytes()); action(obj)
        if rehash: obj["artifact_sha256"] = digest(canonical(obj["payload"]))
        self.write_json(name,obj)
    def test_all_four_captured_artifact_identities_match(self):
        records=json.loads((ORIGINAL / "result-r2.json").read_text())
        for rec in records["comparisons"]:
            with self.subTest(case=rec["name"]):
                actual=reader.load_verified(rec["name"],self.root)
                self.assertEqual(actual["artifact_sha256"],rec["artifact_sha256"])
                self.assertEqual(len(actual["payload"]["variables"]),4)
    def test_json_and_text_use_same_verified_artifact(self):
        raw=reader.read_fixture("later_admission_refusal",evidence_dir=self.root)
        human=reader.read_fixture("later_admission_refusal",output_format="text",evidence_dir=self.root).decode()
        obj=json.loads(raw)
        self.assertIn(obj["artifact_sha256"],human)
        self.assertIn("Target: not_evaluable: unlinked source vintages",human)
        self.assertNotIn("Target: 359241000000",human)
        self.assertIn("DEVELOPMENT FIXTURE",human)
        self.assertIsNone(obj["payload"]["emitted_at"])
    def test_source_capture_time_not_backdated_by_reader(self):
        a=reader.load_verified("first_admission",self.root)
        self.assertNotIn("generated_at",a)
        self.assertNotIn("transition_id",a["payload"])
        self.assertFalse(a["payload"]["comparison_admitted"])
    def test_no_local_write_or_new_file(self):
        before={p.name:digest(p.read_bytes()) for p in self.root.iterdir() if p.is_file()}
        reader.load_verified("first_admission",self.root)
        self.assertEqual(before,{p.name:digest(p.read_bytes()) for p in self.root.iterdir() if p.is_file()})
    def test_unsupported_case_is_rejected_before_file_access(self):
        with patch.object(reader.os,"open",side_effect=AssertionError("unexpected IO")):
            for case in ("../owner-queries", "other_issuer", "", [], None):
                with self.subTest(case=case),self.assertRaises(reader.ReaderRefusal):reader.load_verified(case,self.root)
    def test_bad_format_is_rejected_before_read(self):
        with patch.object(reader,"load_verified",side_effect=AssertionError("unexpected read")):
            with self.assertRaises(reader.ReaderRefusal):reader.read_fixture("first_admission",output_format="html")
    def test_source_bytes_changed_even_if_semantically_same(self):
        p=self.root / "after_a2_admission.response.json";p.write_bytes(p.read_bytes()+b" ");self.refuse()
    def test_owner_rehashed_receipt_cannot_self_attest(self):
        p=self.root / "after_a2_admission.response.json";obj=json.loads(p.read_bytes());obj["coverage"]["value_cells"]=4
        p.write_bytes(canonical(obj));receipts=json.loads((self.root / "owner-queries.json").read_text())
        next(r for r in receipts if r["name"]=="after_a2_admission")["response_sha256"]=digest(p.read_bytes())
        self.write_json("owner-queries.json",receipts);self.refuse()
    def test_method_cutoff_rewrite_is_rejected(self):
        m=json.loads((self.root / "method-before-execution.json").read_text())
        m["requests"]["after_a2_admission"]["policy"]["recorded_at"]="2030-01-01T00:00:00Z"
        self.write_json("method-before-execution.json",m);self.refuse()
    def test_result_digest_rewrite_cannot_self_attest(self):
        records=json.loads((self.root / "result-r2.json").read_text());records["comparisons"][0]["artifact_sha256"]="0"*64
        self.write_json("result-r2.json",records);self.refuse()
    def test_comparison_payload_change_is_rejected(self):
        self.corrupt_comparison(lambda o:o["payload"].__setitem__("product_publication_admitted",True));self.refuse()
    def test_self_rehashed_comparison_is_rejected(self):
        self.corrupt_comparison(lambda o:o["payload"].__setitem__("emitted_at","2020-01-01T00:00:00Z"),True);self.refuse()
    def test_dropped_refused_slot_is_rejected(self):
        self.corrupt_comparison(lambda o:o["payload"]["variables"].pop(),True);self.refuse()
    def test_forged_source_link_is_rejected_before_text_output(self):
        self.corrupt_comparison(lambda o:o["payload"]["variables"][0]["target"]["selected_occurrence_ref"]["source"].__setitem__("source_url","https://untrusted.invalid/"),True)
        with self.assertRaises(reader.ReaderRefusal):reader.read_fixture("later_admission_refusal",output_format="text",evidence_dir=self.root)
    def test_duplicate_comparison_json_key_is_rejected(self):
        p=self.root / "later_admission_refusal.comparison.json";raw=p.read_bytes();p.write_bytes(b'{"payload":null,'+raw.lstrip()[1:]);self.refuse()
    def test_semantically_identical_comparison_whitespace_is_allowed(self):
        p=self.root / "later_admission_refusal.comparison.json";obj=json.loads(p.read_bytes());p.write_text(json.dumps(obj,indent=4))
        self.assertEqual(reader.load_verified("later_admission_refusal",self.root),obj)
    def test_semantic_replay_is_not_replaced_by_hash_check(self):
        original=reader.compare_snapshots
        def broken(*args,**kwargs):
            obj=original(*args,**kwargs);obj["payload"]["counts"]={};return obj
        with patch.object(reader,"compare_snapshots",side_effect=broken):self.refuse()
    def test_missing_input_is_typed_refusal(self):
        (self.root / "after_a2_admission.response.json").unlink();self.refuse()
    def test_file_symlink_is_refused(self):
        path=self.root / "after_a2_admission.response.json";path.unlink();path.symlink_to(ORIGINAL / path.name);self.refuse()
    def test_directory_symlink_is_refused(self):
        link=Path(self.temp.name) / "linked";link.symlink_to(self.root,target_is_directory=True)
        with self.assertRaises(reader.ReaderRefusal):reader.load_verified("first_admission",link)
    def test_fifo_is_refused_without_blocking(self):
        path=self.root / "after_a2_admission.response.json";path.unlink();os.mkfifo(path);self.refuse()
    def test_oversized_file_is_refused(self):
        (self.root / "after_a2_admission.response.json").write_bytes(b" " * 1_048_577);self.refuse()
    def test_malformed_comparison_is_typed_refusal(self):
        (self.root / "later_admission_refusal.comparison.json").write_bytes(b"not json");self.refuse()
    def test_returned_mutation_does_not_change_subsequent_reads(self):
        a=reader.load_verified("first_admission",self.root);expected=deepcopy(a)
        a["payload"]["authority"]["display_only"]=False
        self.assertEqual(reader.load_verified("first_admission",self.root),expected)
    def test_cli_json_is_same_machine_identity(self):
        proc=subprocess.run([sys.executable,str(ROOT / "verified_baseline_reader.py"),"later_admission_refusal","--evidence-dir",str(self.root)],capture_output=True,env=dict(os.environ,PYTHONDONTWRITEBYTECODE="1"),timeout=5)
        self.assertEqual(proc.returncode,0,proc.stderr)
        self.assertEqual(json.loads(proc.stdout),reader.load_verified("later_admission_refusal",self.root))
    def test_cli_refusal_has_no_partial_data_or_host_path(self):
        (self.root / "after_a2_admission.response.json").unlink()
        proc=subprocess.run([sys.executable,str(ROOT / "verified_baseline_reader.py"),"later_admission_refusal","--evidence-dir",str(self.root)],capture_output=True,env=dict(os.environ,PYTHONDONTWRITEBYTECODE="1"),timeout=5)
        self.assertEqual(proc.returncode,2)
        self.assertEqual(proc.stdout,b"")
        self.assertNotIn(str(self.root).encode(),proc.stderr)
        self.assertIn(b"FIXTURE_REFUSED",proc.stderr)

if __name__ == "__main__":unittest.main()

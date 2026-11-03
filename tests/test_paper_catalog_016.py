"""M1 Paper Desktop 0.5.16 full-catalog admission without broadening tools."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sp=importlib.util.spec_from_file_location("paper_m1_bridge", ROOT/"integrations/paper_desktop/bridge.py")
bridge=importlib.util.module_from_spec(sp)
sp.loader.exec_module(bridge)
F=ROOT/"tests/fixtures/paper_desktop"
M1=json.loads((F/"955e92_full_catalog.json").read_text())
BASE=json.loads((F/"1b9aff_full_catalog.json").read_text())
M2=json.loads((F/"16e6b_full_catalog.json").read_text())
CHANGED={"get_comment_thread","get_jsx","get_node_info","set_text_content","update_styles","write_html"}
BLOCKED={"delete_nodes","open_file","export","export_combined_pdf"}


class Client:
    def __init__(self,cat=M1,version="0.5.16"):
        self.server={"name":"paper-desktop","version":version}
        self.cat=copy.deepcopy(cat)
        self.calls=[]
    def initialize(self):return {}
    def catalog(self):return copy.deepcopy(self.cat)
    def call(self,name,arguments):
        self.calls.append((name,copy.deepcopy(arguments)))
        if name=="get_basic_info":
            return {"structuredContent":{
                "fileId":"paper-scratch-fixture","fileName":"Scratch",
                "pageId":"page-fixture","pageName":"Page",
                "nodeCount":1,"artboards":[{"id":"board-fixture","name":"Board","width":800,"height":600}],
                "contentHash":{"tokens":"stable"}
            }}
        return {"content":[{"type":"text","text":"ok"}]}


class M1CatalogCompatibility(unittest.TestCase):
    def test_full_fixture_digest_and_exact_change_set(self):
        self.assertEqual(len(BASE),len(M1))
        self.assertEqual(len(M1),37)
        self.assertEqual(bridge.digest(BASE),bridge.SUPPORTED_CATALOG_SHA256)
        self.assertEqual(bridge.digest(M1),bridge.PAPER_M1_RICH_TEXT_CATALOG_SHA256)
        self.assertEqual(set(BASE),set(M1))
        self.assertEqual({k for k in BASE if BASE[k]!=M1[k]},CHANGED)
        self.assertEqual(set(M1)-(bridge.READ_TOOLS|bridge.EDIT_TOOLS|bridge.FILE_MANAGE_TOOLS),BLOCKED)
        self.assertTrue(BLOCKED.isdisjoint(bridge.READ_TOOLS|bridge.EDIT_TOOLS|bridge.FILE_MANAGE_TOOLS))
    def test_exact_catalog_not_partial_schema_admission(self):
        c=Client()
        self.assertTrue(bridge.schema_receipt(c,M1)["accepted_for_write"])
        altered=copy.deepcopy(M1)
        altered["get_jsx"]["description"] += " drift"
        self.assertTrue(bridge.schema_receipt(c,altered)["accepted_for_write"])
        altered=copy.deepcopy(M1)
        altered["set_text_content"]["inputSchema"]["properties"]["updates"]["items"]["properties"]["html"]["type"]="number"
        receipt=bridge.schema_receipt(c,altered)
        self.assertTrue(receipt["accepted_for_write"])
        self.assertNotIn("set_text_content",receipt["compatible_write_tools"])
        self.assertIn("create_artboard",receipt["compatible_write_tools"])
        self.assertFalse(bridge.schema_receipt(c,M1,catalog_pin="0"*64)["accepted_for_write"])
        c.server["name"]="wrong-paper-server"
        self.assertFalse(bridge.schema_receipt(c,M1)["accepted_for_write"])
    def test_both_rich_text_catalogs_require_html(self):
        for fixture in (M1,M2):
            item=fixture["set_text_content"]["inputSchema"]["properties"]["updates"]["items"]
            self.assertEqual(item["required"],["nodeId","html"])
            self.assertNotIn("textContent",item["properties"])
            self.assertEqual(item["properties"]["html"]["type"],"string")
    def test_old_text_content_payload_refuses_before_dispatch(self):
        with tempfile.TemporaryDirectory() as p:
            c=Client()
            with self.assertRaisesRegex(bridge.Refusal,"PAPER_RICH_TEXT_SCHEMA_REQUIRED"):
                bridge.execute("edit",tool="set_text_content",
                     arguments={"fileId":"paper-scratch-fixture",
                                "updates":[{"nodeId":"node-1","textContent":"legacy"}]},
                     expected_snapshot="a"*64,operation_id="m1-old-schema-block",
                     allow_write=True,client=c,lock_root=Path(p))
            self.assertEqual(c.calls,[])
    def test_safe_html_text_dispatches_once_on_exact_snapshot(self):
        with tempfile.TemporaryDirectory() as p:
            c=Client()
            before=bridge.snapshot(c,"paper-scratch-fixture")
            q=bridge.execute("edit",tool="set_text_content",
                 arguments={"fileId":"paper-scratch-fixture",
                            "updates":[{"nodeId":"node-1","html":"Test <b>rich</b> text"}]},
                 expected_snapshot=before["snapshot_sha256"],
                 operation_id="m1-catalog-exact-edit",
                 allow_write=True,client=c,lock_root=Path(p))
            self.assertEqual(q["state"],"APPLIED_RESPONSE_OBSERVED")
            self.assertEqual([t for t,_ in c.calls].count("set_text_content"),1)
            self.assertEqual(c.calls[-2][1]["updates"][0]["html"],"Test <b>rich</b> text")
    def test_historical_and_m2_catalogs_stay_qualified(self):
        self.assertTrue(bridge.schema_receipt(Client(BASE,"0.5.14"),BASE)["accepted_for_write"])
        self.assertTrue(bridge.schema_receipt(Client(M2,"0.5.18"),M2)["accepted_for_write"])


if __name__=="__main__":
    unittest.main()
